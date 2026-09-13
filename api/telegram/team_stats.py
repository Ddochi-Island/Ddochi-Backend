# 일일보고 방 — 그날 등록(유입)한 사랑이 + 일일보고 제출 집계를 지역방에 보여주는
# "오늘의 추수" 메시지. services/main/src/telegram/generators.js의
# generateTeamStatsMessage 포팅. 레거시의 PROSPECTS/AREAS/ROLES를 이 프로젝트의
# SARANG/MEMBER_AFFILIATION_HISTORIES/POSITION_CODES로 매핑:
#   재가 = SARANG_ACTIVITY_LOGS(EVENT_TYPE='재가처리'), 오프번찾 = SARANG_INFLOW_DETAILS
#   가 있는(=사쉐/번호찾 경로) 오늘 유입, 구역 = MEMBER_AFFILIATION_HISTORIES.DISTRICT_CODE,
#   구역장/부구역장 = MEMBER_POSITION_MAPPINGS(area_lead/sub_area_lead).
# 잎사귀(DAILY_REPORT_LEAVES)와 영업일(22시 롤오버)은 이 리라이트에 대응 데이터가
# 없어 뺐음 — 잎사귀 섹션은 항상 "없습니다" 고정.
import datetime
import logging

from api.telegram import tel_router_client
from api.telegram.team_config import load_team_config, patch_team_config
from api.telegram.team_goals import load_team_goal_total

logger = logging.getLogger('api.telegram.team_stats')

_WEEK = ['일', '월', '화', '수', '목', '금', '토']
_BAR_LEN = 7


def _fmt_md(date_str):
    d = datetime.date.fromisoformat(date_str)
    return f"{d.month:02d}/{d.day:02d}({_WEEK[(d.weekday() + 1) % 7]})"


def _bar(cur, goal):
    if not goal:
        return '⬜️' * _BAR_LEN
    filled = min(_BAR_LEN, round(_BAR_LEN * cur / goal))
    return '🟩' * filled + '⬜️' * (_BAR_LEN - filled)


def _pct(cur, goal):
    return f'{round(cur / goal * 100)}%' if goal else '0%'


def _fetch_districts(client, region_code):
    rows = client.query(
        """SELECT DISTINCT DISTRICT_CODE FROM MEMBER_AFFILIATION_HISTORIES
            WHERE REGION_CODE = :1 AND IS_CURRENT = 1 AND DISTRICT_CODE IS NOT NULL
            ORDER BY DISTRICT_CODE""",
        [region_code],
    )
    return [r['district_code'] for r in rows]


def _fetch_area_leaders(client, region_code):
    """미보고 대상 — 구역장/부구역장만(레거시 정합)."""
    return client.query(
        """SELECT DISTINCT m.NAME, mah.DISTRICT_CODE
             FROM MEMBERS m
             JOIN MEMBER_AFFILIATION_HISTORIES mah ON mah.MEMBER_ID = m.MEMBER_ID AND mah.IS_CURRENT = 1
             JOIN MEMBER_POSITION_MAPPINGS mpm ON mpm.MEMBER_ID = m.MEMBER_ID
            WHERE mah.REGION_CODE = :1 AND m.DELETED_AT IS NULL
              AND mpm.POSITION_CODE IN ('area_lead', 'sub_area_lead')
            ORDER BY mah.DISTRICT_CODE, m.NAME""",
        [region_code],
    )


def _fetch_daily_reports(client, region_code, date_str):
    return client.query(
        """SELECT m.NAME, dr.ACTIVITY, dr.TALK_COUNT, dr.DM_COUNT, dr.QR_COUNT,
                  dr.ONLINE_INTAKE_COUNT, dr.PROMO_LIST, dr.IS_FINAL, dr.SNAP_DISTRICT_CODE
             FROM DAILY_REPORTS dr
             JOIN MEMBERS m ON m.MEMBER_ID = dr.MEMBER_ID
            WHERE dr.SNAP_REGION_CODE = :1 AND dr.REPORT_DATE = TO_DATE(:2, 'YYYY-MM-DD')
            ORDER BY dr.SNAP_DISTRICT_CODE, m.NAME""",
        [region_code, date_str],
    )


def _fetch_approvals(client, region_code, date_str):
    """오늘 재가 처리된 건 — SARANG.RECRUITMENT_TYPE으로 온/오프 구분."""
    return client.query(
        """SELECT s.RECRUITMENT_TYPE, mah.DISTRICT_CODE
             FROM SARANG_ACTIVITY_LOGS al
             JOIN SARANG s ON s.SARANG_ID = al.SARANG_ID
             JOIN MEMBER_AFFILIATION_HISTORIES mah
               ON mah.MEMBER_ID = s.INFLOW_MEMBER_ID AND mah.IS_CURRENT = 1
            WHERE al.EVENT_TYPE = '재가처리'
              AND mah.REGION_CODE = :1
              AND TRUNC(al.CREATED_AT) = TO_DATE(:2, 'YYYY-MM-DD')""",
        [region_code, date_str],
    )


def _fetch_offline_search(client, region_code, date_str):
    """오늘의 오프번찾 — 사쉐/번호찾 경로(SARANG_INFLOW_DETAILS 존재)로 들어온 오늘 유입."""
    return client.query(
        """SELECT spi.NAME AS PI_NAME, im.NAME AS INTRODUCER_NAME, mah.DISTRICT_CODE
             FROM SARANG s
             JOIN SARANG_PERSONAL_INFO spi ON spi.PERSONAL_INFO_ID = s.PERSONAL_INFO_ID
             JOIN SARANG_INFLOW_DETAILS sid ON sid.SARANG_ID = s.SARANG_ID
             JOIN MEMBER_AFFILIATION_HISTORIES mah
               ON mah.MEMBER_ID = s.INFLOW_MEMBER_ID AND mah.IS_CURRENT = 1
             LEFT JOIN MEMBERS im ON im.MEMBER_ID = sid.INTRODUCER_MEMBER_ID
            WHERE mah.REGION_CODE = :1
              AND TRUNC(s.INFLOW_DATE) = TO_DATE(:2, 'YYYY-MM-DD')
              AND s.DELETED_AT IS NULL
            ORDER BY mah.DISTRICT_CODE, s.INFLOW_DATE""",
        [region_code, date_str],
    )


def _promo_items(promo_list_str):
    """DAILY_REPORTS.PROMO_LIST — 프론트가 이미 "학교/방법(도구)" 형태로 join해서
    보냄(원본 배열이 아니라 콤마로 합쳐진 문자열) — 세그먼트 단위로 다시 쪼갬."""
    if not promo_list_str:
        return []
    return [seg.strip() for seg in promo_list_str.split(',') if seg.strip()]


def _build_text(region_code, date_str, reports, approvals, offline_search, districts, leaders, goals):
    now = datetime.datetime.now()

    # ── 집계 ────────────────────────────────────────────────────
    by_district = {dc: {
        'off_act': 0, 'talk': 0, 'shed_reg': 0, 'appr_off': 0,
        'promo': 0, 'dm': 0, 'intake': 0, 'appr_on': 0,
    } for dc in districts}

    def _slot(dc):
        return by_district.setdefault(dc, {
            'off_act': 0, 'talk': 0, 'shed_reg': 0, 'appr_off': 0,
            'promo': 0, 'dm': 0, 'intake': 0, 'appr_on': 0,
        })

    talk = dm = qr = promo_cnt = 0
    reported_names = set()
    act_untact, act_contact, act_off = [], [], []
    todays_promos = []
    for r in reports:
        reported_names.add(r['name'])
        dc = r['snap_district_code'] or '-'
        slot = _slot(dc)
        talk_v, dm_v, qr_v, intake_v = int(r['talk_count'] or 0), int(r['dm_count'] or 0), int(r['qr_count'] or 0), int(r['online_intake_count'] or 0)
        promos = _promo_items(r['promo_list'])
        talk += talk_v; slot['talk'] += talk_v
        dm += dm_v; slot['dm'] += dm_v
        qr += qr_v
        slot['intake'] += intake_v
        promo_cnt += len(promos); slot['promo'] += len(promos)
        for p in promos:
            todays_promos.append(f"{r['name']}/{p}")
        is_final = r['is_final'] == '1'
        item = f"{r['name']}✅" if is_final else r['name']
        if r['activity'] == 'online':
            act_untact.append(item)
        elif r['activity'] == 'offline':
            act_contact.append(item); slot['off_act'] += 1
        elif r['activity'] == 'offlineSearch':
            act_off.append(item); slot['off_act'] += 1

    for a in approvals:
        dc = a['district_code'] or '-'
        slot = _slot(dc)
        if a['recruitment_type'] == 'OFFLINE':
            slot['appr_off'] += 1
        else:
            slot['appr_on'] += 1
    approved_cnt = len(approvals)

    shed_regs = []
    for r in offline_search:
        dc = r['district_code'] or '-'
        _slot(dc)['shed_reg'] += 1
        shed_regs.append(f"{r['pi_name'] or ''}/{r['introducer_name'] or ''}")

    unreported = [ld['name'] for ld in leaders if ld['name'] not in reported_names]

    # ── 조립 ────────────────────────────────────────────────────
    lines = [f'🔥 {region_code}! 오늘의 추수', f"- {_fmt_md(date_str)} {now.strftime('%H:%M')} 기준", '']
    lines.append('[팀 목표 달성률]')
    metrics = [
        ('🗣️', '말걺', talk, goals['talk']),
        ('🤝', '재가', approved_cnt, goals['appr']),
        ('📝', '번찾', len(shed_regs), goals['reg']),
        ('🏫', '홍보', promo_cnt, goals['promo']),
        ('📩', '디엠', dm, goals['dm']),
        ('📷', '큐알', qr, goals['qr']),
    ]
    for icon, label, cur, goal in metrics:
        lines.append(f'{icon} {label} : {_bar(cur, goal)}')
        lines.append(f'   └ {cur} / {goal} ({_pct(cur, goal)})')

    lines.append('---------------------------')
    lines.append('🌱 오늘의 오프번찾')
    lines.append('\n'.join(shed_regs[:20]) if shed_regs else '(등록된 번호찾이 없습니다)')

    lines.append('---------------------------')
    lines.append('🏫 오늘의 홍보학교')
    lines.append('\n'.join(todays_promos[:20]) if todays_promos else '(등록된 홍보학교가 없습니다)')

    lines.append('---------------------------')
    lines.append('🍀 오늘의 잎사귀')
    lines.append('(등록된 잎사귀가 없습니다)')

    lines.append('---------------------------')
    lines.append(f'🛋 미보고 ({len(unreported)}명)')
    if unreported:
        lines.append(', '.join(unreported))
    lines.append('')
    lines.append(f'🌐 비대면활동 ({len(act_untact)}명)')
    lines.append('')
    if act_untact:
        lines.append(', '.join(act_untact))
    lines.append('')
    lines.append(f'👥 대면활동 ({len(act_contact)}명)')
    lines.append('')
    if act_contact:
        lines.append(', '.join(act_contact))
    lines.append('')
    lines.append(f'🏃 오프찾활동 ({len(act_off)}명)')
    lines.append('')
    if act_off:
        lines.append(', '.join(act_off))
    lines.append('')

    lines.append('---------------------------')
    lines.append('')
    lines.append('[오프라인]')
    off_rows = ['구역|활동|말겂|번찾|재가']
    on_rows = ['구역|홍보|디엠|유입|재가']
    for dc in sorted(by_district.keys()):
        s = by_district[dc]
        off_rows.append(f"{dc}|{s['off_act']}|{s['talk']}|{s['shed_reg']}|{s['appr_off']}")
        on_rows.append(f"{dc}|{s['promo']}|{s['dm']}|{s['intake']}|{s['appr_on']}")
    lines.append('<code>' + '\n'.join(off_rows) + '</code>')
    lines.append('')
    lines.append('[온라인]')
    lines.append('<code>' + '\n'.join(on_rows) + '</code>')
    lines.append('')
    lines.append('---------------------------')

    text = '\n'.join(lines)
    return text[:4000] + ('\n…' if len(text) > 4000 else '')


def _dashboard_reply_markup():
    return {'inline_keyboard': [[
        {'text': '📱 앱에서 열기', 'url': 'https://t.me/logDdochi_Bot/entry?startapp=dailyReport'},
        {'text': '🌐 브라우저', 'url': 'https://page.ddochi.cloud/#/daily-report'},
    ]]}


def _build_message(client, region_code, date_str):
    districts = _fetch_districts(client, region_code)
    leaders = _fetch_area_leaders(client, region_code)
    reports = _fetch_daily_reports(client, region_code, date_str)
    approvals = _fetch_approvals(client, region_code, date_str)
    offline_search = _fetch_offline_search(client, region_code, date_str)
    goals = load_team_goal_total(client, region_code)
    return _build_text(region_code, date_str, reports, approvals, offline_search, districts, leaders, goals)


def refresh_team_stats(client, region_code, date_str=None):
    """일일보고 제출 직후 훅 — 기존 메시지가 있을 때만 edit, 없으면 조용히 skip
    (새 메시지 발송은 정각 크론(send_fresh_team_stats) 몫)."""
    date_str = date_str or datetime.date.today().isoformat()
    cfg = load_team_config(client, region_code)
    chat_id = cfg.get('statsChatId')
    if not chat_id:
        return {'skipped': True, 'reason': 'no_chat_id'}

    previous_msg_id = cfg.get('lastStatsMsgId')
    if not previous_msg_id:
        return {'skipped': True, 'reason': 'no_existing_message'}

    text = _build_message(client, region_code, date_str)
    try:
        result = tel_router_client.enqueue(
            'editMessageText',
            {'chat_id': chat_id, 'message_id': previous_msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': _dashboard_reply_markup()},
            await_result=True,
        )
        if result.get('ok'):
            return {'sent': True, 'edited': True}
        if 'message is not modified' in str(result.get('description') or ''):
            return {'sent': True, 'edited': False, 'noChange': True}
    except Exception:
        logger.warning('[team_stats] editMessageText failed', exc_info=True)
    return {'sent': False}


def send_fresh_team_stats(client, region_code):
    """정각 크론 전용 — 매번 새 메시지로 발송하고 성공하면 직전 메시지를 삭제."""
    date_str = datetime.date.today().isoformat()
    cfg = load_team_config(client, region_code)
    chat_id = cfg.get('statsChatId')
    if not chat_id:
        return {'skipped': True, 'reason': 'no_chat_id'}

    text = _build_message(client, region_code, date_str)
    try:
        result = tel_router_client.enqueue(
            'sendMessage',
            {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': _dashboard_reply_markup()},
            await_result=True,
        )
    except Exception:
        logger.warning('[team_stats] send_fresh sendMessage failed', exc_info=True)
        return {'sent': False}

    if not result.get('ok'):
        logger.warning('[team_stats] send_fresh sendMessage rejected: %s', result.get('description'))
        return {'sent': False}

    new_msg_id = result.get('result', {}).get('message_id')
    if not new_msg_id:
        return {'sent': True, 'deletedPrevious': False}

    previous_msg_id = cfg.get('lastStatsMsgId')
    patch_team_config(client, region_code, {'lastStatsMsgId': new_msg_id}, 'system')

    if previous_msg_id and str(previous_msg_id) != str(new_msg_id):
        try:
            tel_router_client.enqueue('deleteMessage', {'chat_id': chat_id, 'message_id': previous_msg_id})
        except Exception:
            logger.warning('[team_stats] delete previous message failed', exc_info=True)

    return {'sent': True, 'newMessageId': new_msg_id, 'deletedPrevious': bool(previous_msg_id)}
