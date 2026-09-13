# 찾기현황판 팀 전체 요약 리스트 — services/main/src/telegram/generators.js의
# generateProspectDashboardMessage + matchingDashboard.js/cronInternal.js의 refresh 포팅.
# 두 갱신 경로가 있음 — refresh_prospect_dashboard(이벤트: 제출/재가/버튼토글) 는 기존
# 메시지를 계속 edit, send_fresh_prospect_dashboard(정각 크론) 는 매번 새로 보내고
# 이전 메시지를 삭제. ponytail: 레거시의 22시 업무일 롤오버 시 "하루 기록 보존"(그
# 시간대만 이전 메시지 삭제 안 함) 예외는 뺐음 — 매시 동일하게 삭제+재발송.
import datetime
import logging

from api.telegram import tel_router_client
from api.telegram.dashboard_send import send_fresh_dashboard
from api.telegram.team_config import load_team_config, patch_team_config

logger = logging.getLogger('api.telegram.prospect_dashboard')


def _fetch_rows(client, team_id):
    return client.query(
        """SELECT s.SARANG_ID, spi.NAME AS PI_NAME, gm.NAME AS GUIDE_NAME,
                  hj.APPROVAL_STATUS, hj.ROUTE, hj.TOOL, hj.TELEGRAM_MSG_ID,
                  hj.HAS_REPLIED, hj.IS_WINDOW_OPENED,
                  TO_CHAR(hj.MATCH_SCHEDULED_AT, 'YYYY-MM-DD') AS MT_DATE,
                  TO_CHAR(hj.MATCH_SCHEDULED_AT, 'HH24:MI') AS MT_TIME,
                  TO_CHAR(al.CREATED_AT, 'YYYY-MM-DD') AS FOUND_APPR_DATE
             FROM SARANG s
             JOIN SARANG_PERSONAL_INFO spi ON spi.PERSONAL_INFO_ID = s.PERSONAL_INFO_ID
             JOIN SARANG_HAB_JAE_YANG hj   ON hj.SARANG_ID = s.SARANG_ID AND hj.IS_ACTIVE = 1
             LEFT JOIN MEMBERS gm          ON gm.MEMBER_ID = hj.GUIDE_MEMBER_ID
             JOIN MEMBER_AFFILIATION_HISTORIES mah
               ON mah.MEMBER_ID = s.INFLOW_MEMBER_ID AND mah.IS_CURRENT = 1
             LEFT JOIN (
               SELECT SARANG_ID, CREATED_AT,
                      ROW_NUMBER() OVER (PARTITION BY SARANG_ID ORDER BY CREATED_AT DESC) AS RN
                 FROM SARANG_ACTIVITY_LOGS WHERE EVENT_TYPE = '재가처리'
             ) al ON al.SARANG_ID = s.SARANG_ID AND al.RN = 1
            WHERE mah.REGION_CODE = :1
              AND s.STAGE IN ('합재양', '재가')
              AND hj.APPROVAL_STATUS != 'rejected'
              AND s.DELETED_AT IS NULL
              AND s.INFLOW_DATE > SYSDATE - 30
            ORDER BY hj.MATCH_SCHEDULED_AT NULLS LAST, s.UPDATED_AT DESC
            FETCH FIRST 200 ROWS ONLY""",
        [team_id],
    )


_WEEK = ['일', '월', '화', '수', '목', '금', '토']


def _fmt_md(date_str):
    if not date_str:
        return '미정'
    d = datetime.date.fromisoformat(date_str)
    return f"{d.month:02d}/{d.day:02d}({_WEEK[(d.weekday() + 1) % 7]})"


def _display_date(r, today):
    """그룹 위치를 정하는 날짜 — 재가된 건은 "재가된 날"에 고정(이후 만남 일정이 밀려도
    그룹은 안 움직임). 재가일은 SARANG_ACTIVITY_LOGS의 '재가처리' 로그 시각에서 가져옴
    (전용 컬럼 없이 기존 로그 재사용 — 재매칭으로 재가가 여러 번 나면 가장 최근 걸 씀).
    재가 전(대기) 건은 만남 예정일 기준으로 그룹핑, 날짜 미정이면 오늘."""
    if r['approval_status'] == 'approved':
        found = r['found_appr_date']
        return datetime.date.fromisoformat(found) if found else today
    return datetime.date.fromisoformat(r['mt_date']) if r['mt_date'] else today


def _build_text(team_id, rows, chat_id):
    now = datetime.datetime.now()
    today = now.date()
    two_days_ago = today - datetime.timedelta(days=2)

    groups = {}
    for r in rows:
        display_date = _display_date(r, today)
        if r['approval_status'] == 'approved' and display_date < two_days_ago:
            continue  # 재가 후 2일 지난 건 목록에서 제거
        key = display_date.isoformat()
        g = groups.setdefault(key, {'total': 0, 'approved': 0, 'items': []})
        g['total'] += 1
        if r['approval_status'] == 'approved':
            g['approved'] += 1
        g['items'].append(r)

    # t.me/c/{id}/{msgId} 딥링크는 슈퍼그룹(id가 -100으로 시작)에서만 유효함 — 기본
    # 그룹/DM이면 링크가 아예 안 걸리니(텔레그램 자체 제약) 깨진 링크 대신 텍스트만 표시.
    chat_id_str = str(chat_id) if chat_id else ''
    tg_chat_part = chat_id_str.removeprefix('-100') if chat_id_str.startswith('-100') else None

    lines = [
        '➖➖➖➖➖➖➖➖➖➖', f'📢 {team_id}지역 찾기 현황판',
        f"- {_fmt_md(now.date().isoformat())} {now.strftime('%H:%M')} 기준", '',
    ]
    if not groups:
        lines.append('현재 진행 중인 만남픽스가 없어 😶')
    for key in sorted(groups.keys()):
        g = groups[key]
        lines.append(f"◾️{_fmt_md(key)}[{g['approved']}/{g['total']}]")
        for it in g['items']:
            icon = '🌕' if it['approval_status'] == 'approved' else '🌑'
            name_str = f"{it['pi_name'] or '-'}/{it['guide_name'] or '-'}"
            replied = '💬' if it['has_replied'] == '1' else '▫️'
            window = '🚪' if it['is_window_opened'] == '1' else '▫️'
            route = it['route'] or ''
            tool = it['tool'] or ''
            path_label = route + (f'({tool})' if tool and tool not in route else '')
            date_prefix = _fmt_md(it['mt_date'])
            time_prefix = it['mt_time'] or ''
            path_text = f"{date_prefix}{time_prefix}_{path_label}"
            if tg_chat_part and it['telegram_msg_id']:
                path_text = f'<a href="https://t.me/c/{tg_chat_part}/{it["telegram_msg_id"]}">{path_text}</a>'
            lines.append(f"<code>{icon}{name_str} {replied}{window}</code>")
            lines.append(f'   ⤷ {path_text}')
        lines.append('')
    lines.append('➖➖➖➖➖➖➖➖➖➖')
    text = '\n'.join(lines)
    return text[:4000] + ('\n…' if len(text) > 4000 else '')


def _backfill_missing_cards(client, rows):
    """리스트엔 있는데 개별 합재양 카드가 아직 이 채팅방에 없는(TELEGRAM_MSG_ID가 없는)
    건들 — 채팅방 연결 전에 만들어졌거나 한 번 발송에 실패한 경우 — 지금 보내서 채움.
    habjaeyang.py를 여기서 import하는 이유: 그쪽이 이 모듈을 이미 import하고 있어서
    (카드 보낸 뒤 리스트도 갱신) 모듈 최상단에서 맞물리면 순환 import가 생김."""
    from api.telegram.habjaeyang import send_habjaeyang_to_telegram

    missing = [r['sarang_id'] for r in rows if not r['telegram_msg_id']]
    for sarang_id in missing:
        try:
            send_habjaeyang_to_telegram(client, sarang_id, refresh_dashboard=False)
        except Exception:
            logger.warning('[prospect_dashboard] backfill failed sarang_id=%s', sarang_id, exc_info=True)
    return bool(missing)


def _dashboard_reply_markup():
    return {'inline_keyboard': [[
        {'text': '📱 앱에서 열기', 'url': 'https://t.me/logDdochi_Bot/entry?startapp=matching'},
        {'text': '🌐 브라우저', 'url': 'https://page.ddochi.cloud/#/matching'},
    ]]}


def refresh_prospect_dashboard(client, team_id, allow_create=True):
    """찾기현황판 리스트 갱신. allow_create=False면 기존 메시지가 있을 때만 edit하고
    없으면 조용히 skip(버튼 토글처럼 가벼운 이벤트에서 새 메시지를 만들지 않기 위함)."""
    cfg = load_team_config(client, team_id)
    chat_id = cfg.get('prospectChatId') or cfg.get('matchingChatId')
    if not chat_id:
        return {'skipped': True, 'reason': 'no_chat_id'}

    rows = _fetch_rows(client, team_id)
    if _backfill_missing_cards(client, rows):
        rows = _fetch_rows(client, team_id)  # 방금 채운 telegram_msg_id를 반영해 다시 조회
    text = _build_text(team_id, rows, chat_id)
    reply_markup = _dashboard_reply_markup()

    previous_msg_id = cfg.get('lastProspectMsgId')
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
            logger.warning('[prospect_dashboard] editMessageText failed', exc_info=True)

    if not allow_create:
        return {'skipped': True, 'reason': 'no_existing_message'}

    try:
        result = tel_router_client.enqueue(
            'sendMessage', {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': reply_markup}, await_result=True,
        )
    except Exception:
        logger.warning('[prospect_dashboard] sendMessage failed', exc_info=True)
        return {'sent': False}

    if not result.get('ok'):
        logger.warning('[prospect_dashboard] sendMessage rejected: %s', result.get('description'))
        return {'sent': False}

    new_msg_id = result.get('result', {}).get('message_id')
    if new_msg_id:
        patch_team_config(client, team_id, {'lastProspectMsgId': new_msg_id}, 'system')
    return {'sent': True, 'edited': False}


def send_fresh_prospect_dashboard(client, team_id):
    """정각 크론 전용 — 매번 새 메시지로 발송. 같은 날 안에서는 직전 메시지를
    삭제하지만, 날짜가 바뀐 뒤 첫 발송이면 전날 마지막 메시지는 하루치 기록으로
    남겨두고 지우지 않음(dashboard_send.send_fresh_dashboard).
    (이벤트 훅용 refresh_prospect_dashboard는 같은 메시지를 계속 edit — 이건 매시 갱신용)"""
    cfg = load_team_config(client, team_id)
    chat_id = cfg.get('prospectChatId') or cfg.get('matchingChatId')
    if not chat_id:
        return {'skipped': True, 'reason': 'no_chat_id'}

    rows = _fetch_rows(client, team_id)
    if _backfill_missing_cards(client, rows):
        rows = _fetch_rows(client, team_id)
    text = _build_text(team_id, rows, chat_id)

    return send_fresh_dashboard(
        client, team_id, chat_id, text, _dashboard_reply_markup(), cfg,
        'lastProspectMsgId', 'lastProspectMsgDate', 'prospect_dashboard',
    )
