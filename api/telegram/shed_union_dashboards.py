# 135/246 연합(사쉐/번호찾 통합) 대시보드 3종 — 통합현황판/TM현황/예약타임테이블.
# services/main/src/telegram/{matchingDashboard,shedTmDashboard,shedScheduleDashboard}.js
# 포팅. 레거시는 PROSPECTS.PATH(shed_1~shed_6, "어느 부스로 들어왔나")로 135/246을
# 나눴는데 이 스키마엔 그 필드가 없어서, 레거시의 예약타임테이블이 이미 쓰던 방식
# (유입담당자의 현재 소속 지역 홀짝)으로 통일 — 새 컬럼 없이 구현.
# BROADCAST_SETTINGS의 TEAM_ID는 리터럴 '135 연합'/'246 연합' 문자열(프론트
# TelegramConnectModal.vue가 그대로 보내는 값) — team_config.py는 TEAM_ID를 임의
# 문자열로 다루므로 그대로 재사용 가능.
import datetime
import logging

from api.telegram import tel_router_client
from api.telegram.dashboard_send import in_broadcast_window, send_fresh_dashboard
from api.telegram.team_config import load_all_team_configs, load_team_config

logger = logging.getLogger('api.telegram.shed_union_dashboards')

_WEEK = ['일', '월', '화', '수', '목', '금', '토']
# TM_RESULT_CODES.RESULT_CODE 기준(한글 자유텍스트 아님 — sql/10_tm_result_codes.sql).
_RESULT_ICON = {'NO_ANSWER': '📵', 'RESERVED_TM': '📅', 'MEET_FIX': '✅', 'UNFIT': '❌', 'REJECT': '🚫', 'INVALID': '⚪️'}
_RESULT_LABEL = {'NO_ANSWER': '부재중', 'RESERVED_TM': '예약 티엠', 'MEET_FIX': '만남 픽스', 'UNFIT': '비합', 'REJECT': '거절', 'INVALID': '무효'}


def _fmt_md(date_str):
    if not date_str:
        return '미정'
    d = datetime.date.fromisoformat(date_str)
    return f"{d.month:02d}/{d.day:02d}({_WEEK[(d.weekday() + 1) % 7]})"


def _union_regions(client, group):
    """group: '135' 또는 '246'. 활성 REGION_CODE 중 숫자로 변환 가능한 것만 홀/짝
    판정 — REGION_CODE가 숫자 문자열이 아닌 경우(있다면)는 걸러짐."""
    rows = client.query(
        "SELECT DISTINCT REGION_CODE FROM MEMBER_AFFILIATION_HISTORIES WHERE IS_CURRENT = 1 AND REGION_CODE IS NOT NULL",
        [],
    )
    want_odd = group == '135'
    out = []
    for r in rows:
        code = r['region_code']
        try:
            n = int(code)
        except (TypeError, ValueError):
            continue
        if (n % 2 == 1) == want_odd:
            out.append(code)
    return out


def _team_id_for_group(group):
    return '135 연합' if group == '135' else '246 연합'


def shed_union_for_sarang(client, sarang_id):
    """이 사랑이가 사쉐(번호찾) 경로인지 + 어느 연합(group, '135'/'246') 소속인지
    판정 — 이벤트훅에서 씀. 사쉐 경로가 아니면 None."""
    row = client.query_one(
        """SELECT mah.REGION_CODE
             FROM SARANG s
             JOIN SARANG_INFLOW_DETAILS sid ON sid.SARANG_ID = s.SARANG_ID
             JOIN MEMBER_AFFILIATION_HISTORIES mah ON mah.MEMBER_ID = s.INFLOW_MEMBER_ID AND mah.IS_CURRENT = 1
            WHERE s.SARANG_ID = :1""",
        [sarang_id],
    )
    if not row or not row['region_code']:
        return None
    try:
        n = int(row['region_code'])
    except (TypeError, ValueError):
        return None
    return '135' if n % 2 == 1 else '246'


def _in_clause(values, start=1):
    placeholders = ', '.join(f':{start + i}' for i in range(len(values)))
    return placeholders, list(values)


def _dashboard_reply_markup(app_path):
    return {'inline_keyboard': [[
        {'text': '📱 앱에서 열기', 'url': f'https://t.me/logDdochi_Bot/entry?startapp={app_path}'},
        {'text': '🌐 브라우저', 'url': f'https://page.ddochi.cloud/#/{app_path}'},
    ]]}


# reply_markup은 항상 dict여야 함 — None을 보내면 텔레그램이
# "Bad Request: object expected as reply markup"로 거부함(버튼 없는 메시지는 빈 배열로).
_NO_MARKUP = {'inline_keyboard': []}


# ── 1. 통합현황판 ────────────────────────────────────────────────────
def _fetch_unified_rows(client, regions):
    if not regions:
        return []
    placeholders, values = _in_clause(regions)
    return client.query(
        f"""SELECT s.SARANG_ID, spi.NAME AS PI_NAME, gm.NAME AS GUIDE_NAME, mah.REGION_CODE,
                   hj.APPROVAL_STATUS, hj.ROUTE, hj.TOOL, hj.TELEGRAM_MSG_ID,
                   hj.HAS_REPLIED, hj.IS_WINDOW_OPENED,
                   TO_CHAR(hj.MATCH_SCHEDULED_AT, 'YYYY-MM-DD') AS MT_DATE,
                   TO_CHAR(hj.MATCH_SCHEDULED_AT, 'HH24:MI') AS MT_TIME,
                   TO_CHAR(al.CREATED_AT, 'YYYY-MM-DD') AS FOUND_APPR_DATE
              FROM SARANG s
              JOIN SARANG_PERSONAL_INFO spi ON spi.PERSONAL_INFO_ID = s.PERSONAL_INFO_ID
              JOIN SARANG_INFLOW_DETAILS sid ON sid.SARANG_ID = s.SARANG_ID
              JOIN SARANG_HAB_JAE_YANG hj    ON hj.SARANG_ID = s.SARANG_ID AND hj.IS_ACTIVE = 1
              LEFT JOIN MEMBERS gm           ON gm.MEMBER_ID = hj.GUIDE_MEMBER_ID
              JOIN MEMBER_AFFILIATION_HISTORIES mah
                ON mah.MEMBER_ID = s.INFLOW_MEMBER_ID AND mah.IS_CURRENT = 1
              LEFT JOIN (
                SELECT SARANG_ID, CREATED_AT,
                       ROW_NUMBER() OVER (PARTITION BY SARANG_ID ORDER BY CREATED_AT DESC) AS RN
                  FROM SARANG_ACTIVITY_LOGS WHERE EVENT_TYPE = '재가처리'
              ) al ON al.SARANG_ID = s.SARANG_ID AND al.RN = 1
             WHERE mah.REGION_CODE IN ({placeholders})
               AND s.STAGE IN ('합재양', '재가')
               AND hj.APPROVAL_STATUS != 'rejected'
               AND s.DELETED_AT IS NULL
               AND s.INFLOW_DATE > SYSDATE - 30
             ORDER BY hj.MATCH_SCHEDULED_AT NULLS LAST, s.UPDATED_AT DESC
             FETCH FIRST 200 ROWS ONLY""",
        values,
    )


def _display_date(r, today):
    if r['approval_status'] == 'approved':
        found = r['found_appr_date']
        return datetime.date.fromisoformat(found) if found else today
    return datetime.date.fromisoformat(r['mt_date']) if r['mt_date'] else today


def _region_tg_chat_part(chat_id):
    """t.me/c/{id}/{msgId} 딥링크는 슈퍼그룹(id가 -100으로 시작)에서만 유효함 —
    prospect_dashboard.py의 같은 처리."""
    chat_id_str = str(chat_id) if chat_id else ''
    return chat_id_str.removeprefix('-100') if chat_id_str.startswith('-100') else None


def _build_unified_text(group, title, rows, region_chat_map=None):
    """region_chat_map: {region_code: chat_id} — 개별 합재양 카드(TELEGRAM_MSG_ID)는
    통합현황판 자체의 채팅방이 아니라 그 사람 소속 지역의 찾기현황판 채팅방에
    올라가 있어서, 딥링크는 반드시 그 지역 chat_id로 만들어야 함(통합현황판이 다른
    채팅방에 연결돼 있으면 메시지 ID가 그 방 기준으로는 의미가 없음)."""
    now = datetime.datetime.now()
    today = now.date()
    two_days_ago = today - datetime.timedelta(days=2)
    region_chat_map = region_chat_map or {}

    groups = {}
    for r in rows:
        display_date = _display_date(r, today)
        if r['approval_status'] == 'approved' and display_date < two_days_ago:
            continue
        key = display_date.isoformat()
        g = groups.setdefault(key, {'total': 0, 'approved': 0, 'items': []})
        g['total'] += 1
        if r['approval_status'] == 'approved':
            g['approved'] += 1
        g['items'].append(r)

    lines = ['➖➖➖➖➖➖➖➖➖➖', f'📢 {title}', f"- {_fmt_md(today.isoformat())} {now.strftime('%H:%M')} 기준", '']
    if not groups:
        lines.append('현재 진행 중인 만남픽스가 없어 😶')
    for key in sorted(groups.keys()):
        g = groups[key]
        lines.append(f"◾️{_fmt_md(key)}[{g['approved']}/{g['total']}]")
        for it in g['items']:
            icon = '🌕' if it['approval_status'] == 'approved' else '🌑'
            name_str = f"{it['pi_name'] or '-'}/{it['guide_name'] or '-'}({it['region_code']}지역)"
            replied = '💬' if it['has_replied'] == '1' else '▫️'
            window = '🚪' if it['is_window_opened'] == '1' else '▫️'
            route = it['route'] or ''
            tool = it['tool'] or ''
            path_label = route + (f'({tool})' if tool and tool not in route else '')
            path_text = f"{_fmt_md(it['mt_date'])}{it['mt_time'] or ''}_{path_label}"
            tg_chat_part = _region_tg_chat_part(region_chat_map.get(it['region_code']))
            if tg_chat_part and it['telegram_msg_id']:
                path_text = f'<a href="https://t.me/c/{tg_chat_part}/{it["telegram_msg_id"]}">{path_text}</a>'
            lines.append(f"<code>{icon}{name_str} {replied}{window}</code>")
            lines.append(f'   ⤷ {path_text}')
        lines.append('')
    lines.append('➖➖➖➖➖➖➖➖➖➖')
    text = '\n'.join(lines)
    return text[:4000] + ('\n…' if len(text) > 4000 else '')


def _build_message_unified(client, group):
    regions = _union_regions(client, group)
    rows = _fetch_unified_rows(client, regions)
    region_configs = load_all_team_configs(client, regions)
    region_chat_map = {r: (cfg.get('prospectChatId') or cfg.get('matchingChatId')) for r, cfg in region_configs.items()}
    title = f"{'선한양치기' if group == '135' else '질적찾기'} 통합 찾기 현황판"
    return _build_unified_text(group, title, rows, region_chat_map)


def refresh_shed_unified(client, group):
    if not in_broadcast_window():
        return {'skipped': True, 'reason': 'outside_broadcast_window'}
    team_id = _team_id_for_group(group)
    cfg = load_team_config(client, team_id)
    chat_id = cfg.get('shedUnifiedChatId')
    if not chat_id:
        return {'skipped': True, 'reason': 'no_chat_id'}
    previous_msg_id = cfg.get('lastShedMsgId')
    if not previous_msg_id:
        return {'skipped': True, 'reason': 'no_existing_message'}
    text = _build_message_unified(client, group)
    try:
        result = tel_router_client.enqueue(
            'editMessageText',
            {'chat_id': chat_id, 'message_id': previous_msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': _dashboard_reply_markup('matching')},
            await_result=True,
        )
        if result.get('ok'):
            return {'sent': True, 'edited': True}
        if 'message is not modified' in str(result.get('description') or ''):
            return {'sent': True, 'edited': False, 'noChange': True}
    except Exception:
        logger.warning('[shed_union] unified editMessageText failed', exc_info=True)
    return {'sent': False}


def send_fresh_shed_unified(client, group):
    team_id = _team_id_for_group(group)
    cfg = load_team_config(client, team_id)
    chat_id = cfg.get('shedUnifiedChatId')
    if not chat_id:
        return {'skipped': True, 'reason': 'no_chat_id'}
    text = _build_message_unified(client, group)
    return send_fresh_dashboard(
        client, team_id, chat_id, text, _dashboard_reply_markup('matching'), cfg,
        'lastShedMsgId', 'lastShedMsgDate', 'shed_union_unified',
    )


# ── 2. TM현황 ────────────────────────────────────────────────────────
def _fetch_tm_registrations(client, regions, date_str):
    if not regions:
        return []
    placeholders, values = _in_clause(regions, start=2)
    return client.query(
        f"""SELECT spi.NAME AS PI_NAME, im.NAME AS INTRODUCER_NAME, mah.REGION_CODE
              FROM SARANG s
              JOIN SARANG_PERSONAL_INFO spi ON spi.PERSONAL_INFO_ID = s.PERSONAL_INFO_ID
              JOIN SARANG_INFLOW_DETAILS sid ON sid.SARANG_ID = s.SARANG_ID
              JOIN MEMBER_AFFILIATION_HISTORIES mah ON mah.MEMBER_ID = s.INFLOW_MEMBER_ID AND mah.IS_CURRENT = 1
              LEFT JOIN MEMBERS im ON im.MEMBER_ID = sid.INTRODUCER_MEMBER_ID
             WHERE TRUNC(s.INFLOW_DATE) = TO_DATE(:1, 'YYYY-MM-DD')
               AND s.DELETED_AT IS NULL
               AND mah.REGION_CODE IN ({placeholders})
             ORDER BY mah.REGION_CODE, im.NAME""",
        [date_str] + values,
    )


def _fetch_tm_logs(client, regions, date_str):
    if not regions:
        return []
    placeholders, values = _in_clause(regions, start=2)
    return client.query(
        f"""SELECT tl.RESULT, tl.SUB_REASON, msrc.LABEL AS SUB_REASON_LABEL, cm.NAME AS CALLER_NAME
              FROM TM_LOGS tl
              JOIN SARANG s ON s.SARANG_ID = tl.SARANG_ID
              JOIN SARANG_INFLOW_DETAILS sid ON sid.SARANG_ID = s.SARANG_ID
              JOIN MEMBER_AFFILIATION_HISTORIES mah ON mah.MEMBER_ID = s.INFLOW_MEMBER_ID AND mah.IS_CURRENT = 1
              LEFT JOIN MEMBERS cm ON cm.MEMBER_ID = tl.CALLER_MEMBER_ID
              LEFT JOIN TM_SUB_REASON_CODES msrc ON msrc.RESULT_CODE = tl.RESULT AND msrc.SUB_CODE = tl.SUB_REASON
             WHERE TRUNC(tl.CREATED_AT) = TO_DATE(:1, 'YYYY-MM-DD')
               AND mah.REGION_CODE IN ({placeholders})""",
        [date_str] + values,
    )


def _fetch_tm_approvals(client, regions, date_str):
    if not regions:
        return []
    placeholders, values = _in_clause(regions, start=2)
    return client.query(
        f"""SELECT spi.NAME AS PI_NAME, im.NAME AS INTRODUCER_NAME, cm.NAME AS CALLER_NAME
              FROM SARANG_ACTIVITY_LOGS al
              JOIN SARANG s ON s.SARANG_ID = al.SARANG_ID
              JOIN SARANG_PERSONAL_INFO spi ON spi.PERSONAL_INFO_ID = s.PERSONAL_INFO_ID
              JOIN SARANG_INFLOW_DETAILS sid ON sid.SARANG_ID = s.SARANG_ID
              JOIN MEMBER_AFFILIATION_HISTORIES mah ON mah.MEMBER_ID = s.INFLOW_MEMBER_ID AND mah.IS_CURRENT = 1
              LEFT JOIN MEMBERS im ON im.MEMBER_ID = sid.INTRODUCER_MEMBER_ID
              LEFT JOIN SARANG_HAB_JAE_YANG hj ON hj.SARANG_ID = s.SARANG_ID AND hj.IS_ACTIVE = 1
              LEFT JOIN MEMBERS cm ON cm.MEMBER_ID = hj.CALLER_MEMBER_ID
             WHERE al.EVENT_TYPE = '재가처리'
               AND TRUNC(al.CREATED_AT) = TO_DATE(:1, 'YYYY-MM-DD')
               AND mah.REGION_CODE IN ({placeholders})""",
        [date_str] + values,
    )


_DIVIDER = '---------------------------'


def _build_tm_text(group, label, regs, logs, approvals):
    now = datetime.datetime.now()
    # 성사 = 만남픽스만이 아니라 전화가 연결돼서 뭐든 진행된 시도(부재중만 제외).
    success_count = sum(1 for l in logs if l['result'] != 'NO_ANSWER')

    by_region = {}
    for r in regs:
        by_region.setdefault(r['region_code'], []).append(r)

    lines = [
        f'🐾📞 {label} 오늘의 현황',
        f"- {_fmt_md(now.date().isoformat())} {now.strftime('%H:%M')} 기준",
        '',
        f"📋 번호찾 {len(regs)}명 · 📞 시도 {len(logs)}건 · ✅ 성사 {success_count}건 · 🤝 합자찾 {len(approvals)}명",
        '',
        _DIVIDER,
        f'📋 번호찾 총 {len(regs)}명',
    ]
    if by_region:
        for rc in sorted(by_region.keys()):
            names = ', '.join(f"{r['introducer_name'] or '-'}→{r['pi_name']}" for r in by_region[rc])
            lines.append(f'◾️{rc}지역 ({len(by_region[rc])}명): {names}')
    else:
        lines.append('없음')

    lines.append(_DIVIDER)
    lines.append('📞 티엠 현황')
    lines.append(f'📝 시도 {len(logs)}건 · ✅ 성사 {success_count}건')
    lines.append('')
    if logs:
        by_caller = {}
        for l in logs:
            slot = by_caller.setdefault(l['caller_name'] or '-', {'total': 0, 'success': 0})
            slot['total'] += 1
            if l['result'] != 'NO_ANSWER':
                slot['success'] += 1
        ranked = sorted(by_caller.items(), key=lambda x: -x[1]['total'])
        for i, (name, s) in enumerate(ranked):
            crown = '👑' if i == 0 else '▫️'
            lines.append(f"{crown} {name}  {s['total']}건 / {s['success']}건 성사")
        for target in ('UNFIT', 'REJECT'):
            reasons = [l['sub_reason_label'] for l in logs if l['result'] == target and l['sub_reason_label']]
            if reasons:
                by_reason = {}
                for rs in reasons:
                    by_reason.setdefault(rs, 0)
                    by_reason[rs] += 1
                lines.append(f"{_RESULT_LABEL[target]} 사유: " + ', '.join(f'{rs}({c})' for rs, c in by_reason.items()))
    else:
        lines.append('없음')

    lines.append(_DIVIDER)
    lines.append(f'🤝 합자찾 총 {len(approvals)}명')
    if approvals:
        for a in approvals:
            lines.append(f"섭:{a['pi_name']}  유:{a['introducer_name'] or '-'}  티:{a['caller_name'] or '-'}")
    else:
        lines.append('없음')

    text = '\n'.join(lines)
    return text[:4000] + ('\n…' if len(text) > 4000 else '')


def _build_message_tm(client, group):
    regions = _union_regions(client, group)
    date_str = datetime.date.today().isoformat()
    regs = _fetch_tm_registrations(client, regions, date_str)
    logs = _fetch_tm_logs(client, regions, date_str)
    approvals = _fetch_tm_approvals(client, regions, date_str)
    label = '선한양치기' if group == '135' else '질적찾기'
    return _build_tm_text(group, label, regs, logs, approvals)


def refresh_shed_tm(client, group):
    if not in_broadcast_window():
        return {'skipped': True, 'reason': 'outside_broadcast_window'}
    team_id = _team_id_for_group(group)
    cfg = load_team_config(client, team_id)
    chat_id = cfg.get('tmDashChatId')
    if not chat_id:
        return {'skipped': True, 'reason': 'no_chat_id'}
    previous_msg_id = cfg.get('lastTmMsgId')
    if not previous_msg_id:
        return {'skipped': True, 'reason': 'no_existing_message'}
    text = _build_message_tm(client, group)
    try:
        result = tel_router_client.enqueue(
            'editMessageText',
            {'chat_id': chat_id, 'message_id': previous_msg_id, 'text': text, 'parse_mode': 'HTML'},
            await_result=True,
        )
        if result.get('ok'):
            return {'sent': True, 'edited': True}
        if 'message is not modified' in str(result.get('description') or ''):
            return {'sent': True, 'edited': False, 'noChange': True}
    except Exception:
        logger.warning('[shed_union] tm editMessageText failed', exc_info=True)
    return {'sent': False}


def send_fresh_shed_tm(client, group):
    team_id = _team_id_for_group(group)
    cfg = load_team_config(client, team_id)
    chat_id = cfg.get('tmDashChatId')
    if not chat_id:
        return {'skipped': True, 'reason': 'no_chat_id'}
    text = _build_message_tm(client, group)
    return send_fresh_dashboard(
        client, team_id, chat_id, text, _NO_MARKUP, cfg,
        'lastTmMsgId', 'lastTmMsgDate', 'shed_union_tm',
    )


# ── 3. 예약타임테이블 ──────────────────────────────────────────────────
def _fetch_reservations(client, regions):
    if not regions:
        return []
    placeholders, values = _in_clause(regions, start=1)
    return client.query(
        f"""SELECT * FROM (
              SELECT spi.NAME AS PI_NAME, mah.REGION_CODE, im.NAME AS INTRODUCER_NAME, cm.NAME AS CALLER_NAME,
                     TO_CHAR(tl.RESERVED_TM_AT, 'YYYY-MM-DD') AS RES_DATE,
                     TO_CHAR(tl.RESERVED_TM_AT, 'HH24:MI') AS RES_TIME,
                     ROW_NUMBER() OVER (PARTITION BY s.SARANG_ID ORDER BY tl.CREATED_AT DESC) AS RN
                FROM TM_LOGS tl
                JOIN SARANG s ON s.SARANG_ID = tl.SARANG_ID
                JOIN SARANG_PERSONAL_INFO spi ON spi.PERSONAL_INFO_ID = s.PERSONAL_INFO_ID
                JOIN SARANG_INFLOW_DETAILS sid ON sid.SARANG_ID = s.SARANG_ID
                JOIN MEMBER_AFFILIATION_HISTORIES mah ON mah.MEMBER_ID = s.INFLOW_MEMBER_ID AND mah.IS_CURRENT = 1
                LEFT JOIN MEMBERS im ON im.MEMBER_ID = sid.INTRODUCER_MEMBER_ID
                LEFT JOIN MEMBERS cm ON cm.MEMBER_ID = tl.CALLER_MEMBER_ID
               WHERE tl.RESULT = 'RESERVED_TM'
                 AND tl.RESERVED_TM_AT IS NOT NULL
                 AND tl.RESERVED_TM_AT >= SYSTIMESTAMP - INTERVAL '3' DAY
                 AND mah.REGION_CODE IN ({placeholders})
            ) WHERE RN = 1
            ORDER BY RES_DATE NULLS LAST, RES_TIME""",
        values,
    )


def _fetch_pending_count(client, regions):
    if not regions:
        return 0
    placeholders, values = _in_clause(regions, start=1)
    row = client.query_one(
        f"""SELECT COUNT(*) AS CNT
              FROM SARANG s
              JOIN SARANG_INFLOW_DETAILS sid ON sid.SARANG_ID = s.SARANG_ID
              JOIN MEMBER_AFFILIATION_HISTORIES mah ON mah.MEMBER_ID = s.INFLOW_MEMBER_ID AND mah.IS_CURRENT = 1
             WHERE s.STAGE NOT IN ('재가')
               AND s.DELETED_AT IS NULL
               AND s.INFLOW_DATE > SYSDATE - 30
               AND mah.REGION_CODE IN ({placeholders})""",
        values,
    )
    return int(row['cnt']) if row else 0


def _build_sched_text(group, label, rows, pending_count):
    now = datetime.datetime.now()
    today = now.date().isoformat()

    by_date = {}
    no_date = []
    for r in rows:
        if r['res_date']:
            by_date.setdefault(r['res_date'], []).append(r)
        else:
            no_date.append(r)

    lines = [
        '➖➖➖➖➖➖➖➖➖➖', f'📅 {label} 티엠 예약 타임테이블',
        f"- {_fmt_md(today)} {now.strftime('%H:%M')} 기준 · 금일 {len(by_date.get(today, []))}건",
    ]
    if pending_count:
        lines.append(f'⚠️ 번호찾 미재가 {pending_count}건')
    lines.append('')

    if not by_date and not no_date:
        lines.append('(예약된 티엠이 없어)')
    for key in sorted(by_date.keys()):
        marker = '🌈' if key == today else '▫️'
        lines.append(f'{marker} {_fmt_md(key)}')
        for r in by_date[key]:
            person = r['caller_name'] or r['introducer_name'] or '-'
            lines.append(f"  {r['res_time']}  {r['pi_name']} | {r['region_code']}지역 | {r['introducer_name'] or '-'} | {person}")
        lines.append('')
    if no_date:
        lines.append('🌈 날짜 미정')
        for r in no_date:
            person = r['caller_name'] or r['introducer_name'] or '-'
            lines.append(f"  {r['pi_name']} | {r['region_code']}지역 | {r['introducer_name'] or '-'} | {person}")

    lines.append('➖➖➖➖➖➖➖➖➖➖')
    text = '\n'.join(lines)
    return text[:4000] + ('\n…' if len(text) > 4000 else '')


def _build_message_sched(client, group):
    regions = _union_regions(client, group)
    rows = _fetch_reservations(client, regions)
    pending = _fetch_pending_count(client, regions)
    label = '선한양치기' if group == '135' else '질적찾기'
    return _build_sched_text(group, label, rows, pending)


def refresh_shed_sched(client, group):
    if not in_broadcast_window():
        return {'skipped': True, 'reason': 'outside_broadcast_window'}
    team_id = _team_id_for_group(group)
    cfg = load_team_config(client, team_id)
    chat_id = cfg.get('schedDashChatId')
    if not chat_id:
        return {'skipped': True, 'reason': 'no_chat_id'}
    previous_msg_id = cfg.get('lastSchedMsgId')
    if not previous_msg_id:
        return {'skipped': True, 'reason': 'no_existing_message'}
    text = _build_message_sched(client, group)
    try:
        result = tel_router_client.enqueue(
            'editMessageText',
            {'chat_id': chat_id, 'message_id': previous_msg_id, 'text': text, 'parse_mode': 'HTML'},
            await_result=True,
        )
        if result.get('ok'):
            return {'sent': True, 'edited': True}
        if 'message is not modified' in str(result.get('description') or ''):
            return {'sent': True, 'edited': False, 'noChange': True}
    except Exception:
        logger.warning('[shed_union] sched editMessageText failed', exc_info=True)
    return {'sent': False}


def send_fresh_shed_sched(client, group):
    team_id = _team_id_for_group(group)
    cfg = load_team_config(client, team_id)
    chat_id = cfg.get('schedDashChatId')
    if not chat_id:
        return {'skipped': True, 'reason': 'no_chat_id'}
    text = _build_message_sched(client, group)
    return send_fresh_dashboard(
        client, team_id, chat_id, text, _NO_MARKUP, cfg,
        'lastSchedMsgId', 'lastSchedMsgDate', 'shed_union_sched',
    )
