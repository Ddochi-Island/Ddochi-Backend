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
    마이그레이션 이후 너무 길어 보인다는 사용자 신고로 30일에 맞춤(2026-09-26)."""
    return client.query(
        """SELECT s.SARANG_ID, smh.MATCH_ID, smh.MATCH_DEGREE, smh.ATTEMPT_COUNT,
                  TO_CHAR(smh.MATCHED_AT, 'YYYY-MM-DD') AS MT_DATE,
                  TO_CHAR(smh.MATCHED_AT, 'HH24:MI') AS MT_TIME,
                  smh.RESULT, mrc.LABEL AS RESULT_LABEL, msrc.LABEL AS SUB_REASON_LABEL,
                  spi.NAME AS PI_NAME, gm.NAME AS GUIDE_NAME,
                  COALESCE(tcm.NAME, hj.TEACHER_NAME_OVERRIDE) AS TEACHER_NAME
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
            WHERE mah.REGION_CODE = :1
              AND s.STAGE NOT IN ('유입', '티엠')
              AND s.DELETED_AT IS NULL
              AND s.CREATED_AT >= SYSTIMESTAMP - INTERVAL '30' DAY
            ORDER BY s.SARANG_ID, smh.MATCH_DEGREE, smh.ATTEMPT_COUNT
            FETCH FIRST 500 ROWS ONLY""",
        [team_id],
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
    by_sarang = {}
    for r in rows:
        by_sarang.setdefault(r['sarang_id'], []).append(r)

    groups = {}
    for hist in by_sarang.values():
        for i, r in enumerate(hist):
            nxt = hist[i + 1] if i + 1 < len(hist) else None
            prev = hist[i - 1] if i > 0 else None
            # 직전 시도가 2차만남으로 넘어간 결과였다면, 이 행이 바로 그 2차만남 자리.
            is_2cha = bool(prev and prev['result'] == 'SECOND_MEET')
            key = r['mt_date'] or '미정'
            groups.setdefault(key, []).append({
                'time': (r['mt_time'] or '-') + ('✌️' if is_2cha else ''),
                'name': r['pi_name'] or '', 'guide': r['guide_name'] or '',
                'teacher': r['teacher_name'] or '', 'outcome': _outcome(r, nxt),
            })

    lines = ['➖➖➖➖➖➖➖➖➖➖', f'📢 {team_id}지역 매칭 현황판', '']
    if not groups:
        lines.append('예정된 매칭이 없어 😶')
    else:
        def sort_key(k):
            return '9999-99-99' if k == '미정' else k

        for key in sorted(groups.keys(), key=sort_key):
            lines.append(f"◾️ {_fmt_md(key)}" if key != '미정' else '◾️ 날짜 미정')
            items = sorted(groups[key], key=lambda it: it['time'])
            for it in items:
                lines.append(f"<code>{it['time']}|{it['name']}|{it['guide']}|{it['teacher']}|{it['outcome']}</code>")
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
