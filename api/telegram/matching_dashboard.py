# 매칭현황판 팀 전체 요약 리스트 — services/main/src/telegram/generators.js의
# generateMatchingDashboardMessage 포팅 + 웹(MatchingHistoryScreen.vue)과 동일한
# "밀림/2차만남이면 다음 날짜까지 같이 보여주고, 그 다음 시도는 새 행으로 따로
# 보여준다" 방식으로 맞춤 — 최신 시도 하나만 보여주던 이전 버전에서 확장.
import datetime
import logging

from api.telegram import tel_router_client
from api.telegram.dashboard_send import in_broadcast_window, send_fresh_dashboard
from api.telegram.team_config import load_team_config, patch_team_config

logger = logging.getLogger('api.telegram.matching_dashboard')

_WEEK = ['일', '월', '화', '수', '목', '금', '토']

# assets.py의 _MATCH_RESULT_ICON과 동일 — import 순환(assets.py가 이 모듈을 이미
# import함) 피하려고 작은 상수라 그냥 복사해서 둠.
_MATCH_RESULT_ICON = {'CANCEL': '❌', 'DELAY': '❌', 'UNFIT': '⭕️', 'DROPOUT': '⭕️', 'SECOND_MEET': '⭕️', 'CONSULT_WIN': '⭕️'}
_RESCHEDULE_RESULTS = ('DELAY', 'SECOND_MEET')

# 수지역장/전도교관용 "전체 지역" 통합 매칭현황판 — 135 연합/246 연합과 같은 방식의
# 특수 TEAM_ID(BROADCAST_SETTINGS.TEAM_ID='수지역', matchingChatId로 페어링).
# 2026-09-27 사용자 요청. 크론 순회(list_prospect_chat_team_ids)는 코드 변경
# 없이 이 TEAM_ID도 그대로 돌게 됨 — matchingChatId만 있으면 되는 구조라서.
_ALL_REGIONS_TEAM_ID = '수지역'


def _fmt_md(date_str):
    if not date_str:
        return '미정'
    d = datetime.date.fromisoformat(date_str)
    return f"{d.month:02d}/{d.day:02d}({_WEEK[(d.weekday() + 1) % 7]})"


def _fetch_rows(client, team_id):
    """팀의 활성 사랑이(재가 이후, 최근 30일)에 대해 SARANG_MATCH_HISTORIES 전체 시도를
    시간순으로 가져옴 — 밀림/2차만남 다음 날짜를 보여주려면 시도 하나가 아니라
    사람당 전체 이력이 필요함(get_assets의 match_by_id 2-pass와 같은 이유).
    레거시 generateMatchingDashboardMessage도 BUSINESS_DATE 기준 30일 윈도우를
    씀(services/main/src/telegram/generators.js:454) — 60일은 실서버 데이터
    마이그레이션 이후 너무 길어 보인다는 사용자 신고로 30일에 맞춤(2026-09-26).
    team_id가 _ALL_REGIONS_TEAM_ID면 REGION_CODE 필터 없이 전 지역을 가져옴 —
    대신 6개 지역치를 다 합치면 글자수 제한(4000자)에 걸려서 통째로 잘리길래
    (실제 겪음, 271건→중간에 잘림) 만남 예정일(MATCHED_AT) 기준 오늘부터 3일
    후까지(과거 제외, 사용자 요청 2026-09-27)에 해당하는 시도가 하나라도 있는
    사람만으로 좁힘 — 등록일(CREATED_AT) 기준이 아니라 만남 날짜 기준인 점
    주의. 사람 단위로만 좁히고 그 사람의 전체 이력은 그대로 다 가져옴(밀림/
    2차만남 다음 날짜 계산에 prev/next가 필요해서) — 화면에 실제로 보일
    범위 밖 시도 제외는 _build_text가 함."""
    is_all = team_id == _ALL_REGIONS_TEAM_ID
    region_clause = '' if is_all else 'AND mah.REGION_CODE = :1'
    args = [] if is_all else [team_id]
    if is_all:
        scope_clause = """AND EXISTS (
              SELECT 1 FROM SARANG_MATCH_HISTORIES x
               WHERE x.SARANG_ID = s.SARANG_ID
                 AND x.MATCHED_AT BETWEEN TRUNC(SYSDATE) AND TRUNC(SYSDATE) + INTERVAL '4' DAY
            )"""
    else:
        scope_clause = "AND s.CREATED_AT >= SYSTIMESTAMP - INTERVAL '30' DAY"
    return client.query(
        f"""SELECT s.SARANG_ID, smh.MATCH_ID, smh.MATCH_DEGREE, smh.ATTEMPT_COUNT,
                  TO_CHAR(smh.MATCHED_AT, 'YYYY-MM-DD') AS MT_DATE,
                  TO_CHAR(smh.MATCHED_AT, 'HH24:MI') AS MT_TIME,
                  smh.RESULT, mrc.LABEL AS RESULT_LABEL, msrc.LABEL AS SUB_REASON_LABEL,
                  spi.NAME AS PI_NAME, gm.NAME AS GUIDE_NAME,
                  COALESCE(tcm.NAME, hj.TEACHER_NAME_OVERRIDE) AS TEACHER_NAME,
                  mah.REGION_CODE AS REGION
             FROM SARANG s
             JOIN SARANG_PERSONAL_INFO spi ON spi.PERSONAL_INFO_ID = s.PERSONAL_INFO_ID
             JOIN SARANG_MATCH_HISTORIES smh ON smh.SARANG_ID = s.SARANG_ID
             LEFT JOIN SARANG_HAB_JAE_YANG hj ON hj.SARANG_ID = s.SARANG_ID AND hj.IS_ACTIVE = 1
             LEFT JOIN MEMBERS gm  ON gm.MEMBER_ID = hj.GUIDE_MEMBER_ID
             LEFT JOIN MEMBERS tcm ON tcm.MEMBER_ID = hj.TEACHER_MEMBER_ID
             LEFT JOIN MATCH_RESULT_CODES mrc ON mrc.RESULT_CODE = smh.RESULT
             LEFT JOIN MATCH_SUB_REASON_CODES msrc ON msrc.RESULT_CODE = smh.RESULT AND msrc.SUB_CODE = smh.SUB_REASON
             JOIN MEMBER_AFFILIATION_HISTORIES mah
               ON mah.MEMBER_ID = s.INFLOW_MEMBER_ID AND mah.IS_CURRENT = 1
            WHERE s.STAGE NOT IN ('유입', '티엠')
              {region_clause}
              AND s.DELETED_AT IS NULL
              {scope_clause}
            ORDER BY s.SARANG_ID, smh.MATCH_DEGREE, smh.ATTEMPT_COUNT
            FETCH FIRST 2000 ROWS ONLY""",
        args,
    )


def _outcome(row, next_row):
    """결과가 있는 행만 라벨을 보여줌(+밀림/2차만남이면 다음 날짜) — 결과 없는(아직
    안 만난) 행은 준비완료/교사구함 같은 문구 없이 빈칸으로 둠."""
    if not row['result']:
        return ''
    text = f"{_MATCH_RESULT_ICON.get(row['result'], '')}{row['sub_reason_label'] or row['result_label']}"
    if row['result'] in _RESCHEDULE_RESULTS:
        text += f" ({_fmt_md(next_row['mt_date'] if next_row else None)})"
    return text


def _build_text(team_id, rows):
    # 결과 난(RESULT IS NOT NULL) 시도는 그 날짜로부터 2일 지나면 목록에서 뺌 —
    # prospect_dashboard.py의 "재가 후 2일 지난 건 제거"와 동일 패턴(사용자 요청,
    # 2026-09-27 — 처음엔 "지나면 바로"로 바꿨다가 유예 2일 유지로 재확정).
    # 아직 결과 없는(미정/예정) 시도는 그대로 계속 보임.
    today = datetime.date.today()
    two_days_ago = today - datetime.timedelta(days=2)
    is_all = team_id == _ALL_REGIONS_TEAM_ID
    # 수지역(전체) 보드는 만남 예정일 기준 오늘부터 3일 후까지(과거는 제외)만
    # 화면에 보임 — _fetch_rows는 사람 단위로만 넓게 가져오므로(prev/next 계산용)
    # 실제 표시 범위는 여기서 자름.
    window_start = today
    window_end = today + datetime.timedelta(days=3)

    by_sarang = {}
    for r in rows:
        by_sarang.setdefault(r['sarang_id'], []).append(r)

    groups = {}
    for hist in by_sarang.values():
        for i, r in enumerate(hist):
            nxt = hist[i + 1] if i + 1 < len(hist) else None
            prev = hist[i - 1] if i > 0 else None
            if r['result'] and r['mt_date'] and datetime.date.fromisoformat(r['mt_date']) < two_days_ago:
                continue
            if is_all and r['mt_date'] and not (window_start <= datetime.date.fromisoformat(r['mt_date']) <= window_end):
                continue
            # 직전 시도가 2차만남으로 넘어간 결과였다면, 이 행이 바로 그 2차만남 자리.
            is_2cha = bool(prev and prev['result'] == 'SECOND_MEET')
            key = r['mt_date'] or '미정'
            groups.setdefault(key, []).append({
                'time': (r['mt_time'] or '-') + ('✌️' if is_2cha else ''),
                'name': r['pi_name'] or '', 'guide': r['guide_name'] or '',
                'teacher': r['teacher_name'] or '', 'outcome': _outcome(r, nxt),
                'region': r['region'] or '-', 'sarang_id': r['sarang_id'],
            })

    title = '📢 수지역 매칭 현황판' if is_all else f'📢 {team_id}지역 매칭 현황판'
    lines = ['➖➖➖➖➖➖➖➖➖➖', title, '']
    if not groups:
        lines.append('예정된 매칭이 없어 😶')
    else:
        def sort_key(k):
            return '9999-99-99' if k == '미정' else k

        for key in sorted(groups.keys(), key=sort_key):
            lines.append(f"◾️ {_fmt_md(key)}" if key != '미정' else '◾️ 날짜 미정')
            items = sorted(groups[key], key=lambda it: it['time'])
            for it in items:
                # 전체(수지역) 보드만 지역 태그를 맨 앞에 붙임 — 개별 지역 보드는 기존 그대로.
                region_prefix = f"{it['region']}지역|" if is_all else ''
                lines.append(f"<code>{region_prefix}{it['time']}|{it['name']}|{it['guide']}|{it['teacher']}|{it['outcome']}</code>")
                # 교사 미배정 + 아직 결과 없는 건만 탭형 명령 노출(개별 지역 보드 한정, 수지역
                # 통합 보드는 대상 아님) — 8자리 서픽스라 <code> 밖 평문으로 둬야 텔레그램이
                # bot_command로 인식해서 탭하면 입력창에 자동완성됨(32자 넘으면 인식 안 됨).
                if not is_all and not it['teacher'] and not it['outcome']:
                    lines.append(f"　　└ 교사 입력: /t_{it['sarang_id'][-8:]} 이름")
            lines.append('')

    lines.append('➖➖➖➖➖➖➖➖➖➖')
    text = '\n'.join(lines)
    return text[:4000] + ('\n…' if len(text) > 4000 else '')


def _dashboard_reply_markup():
    return {'inline_keyboard': [[
        {'text': '매칭 절대지켜! 🛡️', 'url': 'https://t.me/logDdochi_Bot/entry?startapp=matching'},
    ]]}


def refresh_matching_dashboard(client, team_id, allow_create=True):
    """매칭현황판 리스트 갱신 — prospect_dashboard.refresh_prospect_dashboard와 동일한
    edit-우선/allow_create 패턴. 06~23시 발송 시간대 밖이면 웹 이벤트로 인한 갱신도
    건너뜀 — 그 시간대 메시지는 전날 마감 기록이라 더 이상 안 건드림."""
    if not in_broadcast_window():
        return {'skipped': True, 'reason': 'outside_broadcast_window'}

    cfg = load_team_config(client, team_id)
    chat_id = cfg.get('matchingChatId')
    if not chat_id:
        return {'skipped': True, 'reason': 'no_chat_id'}

    rows = _fetch_rows(client, team_id)
    text = _build_text(team_id, rows)
    reply_markup = _dashboard_reply_markup()

    previous_msg_id = cfg.get('lastMatchingMsgId')
    if previous_msg_id:
        try:
            result = tel_router_client.enqueue(
                'editMessageText',
                {'chat_id': chat_id, 'message_id': previous_msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': reply_markup},
                await_result=True,
            )
            if result.get('ok'):
                return {'sent': True, 'edited': True}
            if 'message is not modified' in str(result.get('description') or ''):
                return {'sent': True, 'edited': False, 'noChange': True}
        except Exception:
            logger.warning('[matching_dashboard] editMessageText failed', exc_info=True)

    if not allow_create:
        return {'skipped': True, 'reason': 'no_existing_message'}

    try:
        result = tel_router_client.enqueue(
            'sendMessage', {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': reply_markup}, await_result=True,
        )
    except Exception:
        logger.warning('[matching_dashboard] sendMessage failed', exc_info=True)
        return {'sent': False}

    if not result.get('ok'):
        logger.warning('[matching_dashboard] sendMessage rejected: %s', result.get('description'))
        return {'sent': False}

    new_msg_id = result.get('result', {}).get('message_id')
    if new_msg_id:
        patch_team_config(client, team_id, {'lastMatchingMsgId': new_msg_id}, 'system')
    return {'sent': True, 'edited': False}


def send_fresh_matching_dashboard(client, team_id):
    """정각 크론 전용 — 매번 새 메시지로 발송. 같은 날 안에서는 직전 메시지를
    삭제하지만, 날짜가 바뀐 뒤 첫 발송이면 전날 마지막 메시지는 하루치 기록으로
    남겨두고 지우지 않음(dashboard_send.send_fresh_dashboard)."""
    cfg = load_team_config(client, team_id)
    chat_id = cfg.get('matchingChatId')
    if not chat_id:
        return {'skipped': True, 'reason': 'no_chat_id'}

    rows = _fetch_rows(client, team_id)
    text = _build_text(team_id, rows)

    return send_fresh_dashboard(
        client, team_id, chat_id, text, _dashboard_reply_markup(), cfg,
        'lastMatchingMsgId', 'lastMatchingMsgDate', 'matching_dashboard',
    )


def refresh_matching_dashboard_for_sarang(client, sarang_id):
    """호출부가 team_id를 모를 때 쓰는 편의 함수 — 결과입력/재가/날짜수정 같은
    sarang_id 단위 이벤트 훅에서 바로 부를 수 있게 INFLOW_MEMBER_ID로 team을 resolve."""
    row = client.query_one(
        """SELECT mah.REGION_CODE AS TEAM_ID
             FROM SARANG s
             JOIN MEMBER_AFFILIATION_HISTORIES mah
               ON mah.MEMBER_ID = s.INFLOW_MEMBER_ID AND mah.IS_CURRENT = 1
            WHERE s.SARANG_ID = :1""",
        [sarang_id],
    )
    if not row or not row['team_id']:
        return {'skipped': True, 'reason': 'team_missing'}
    return refresh_matching_dashboard(client, row['team_id'], allow_create=True)
