# 일일보고 방 — 그날 등록(유입)한 사랑이 + 일일보고 제출 집계를 지역방에 보여주는
# 메시지. services/main/src/telegram/generators.js의 generateTeamStatsMessage
# 포팅이지만, 이 프로젝트 스키마엔 AREAS/PROSPECTS/telegram_goals가 없어서 목표
# 달성률 바/구역장 필터링/shed 확정 번호찾 섹션은 뺐음(자세한 사유는 세션 플랜 문서).
import datetime
import logging

from api.telegram import tel_router_client
from api.telegram.team_config import load_team_config, patch_team_config

logger = logging.getLogger('api.telegram.team_stats')

_WEEK = ['일', '월', '화', '수', '목', '금', '토']


def _fmt_md(date_str):
    if not date_str:
        return '-'
    d = datetime.date.fromisoformat(date_str)
    return f"{d.month:02d}/{d.day:02d}({_WEEK[(d.weekday() + 1) % 7]})"


def _fetch_registrations(client, region_code, date_str):
    return client.query(
        """SELECT spi.NAME AS PI_NAME, im.NAME AS INFLOW_NAME, mah.DISTRICT_CODE
             FROM SARANG s
             JOIN SARANG_PERSONAL_INFO spi ON spi.PERSONAL_INFO_ID = s.PERSONAL_INFO_ID
             JOIN MEMBERS im ON im.MEMBER_ID = s.INFLOW_MEMBER_ID
             JOIN MEMBER_AFFILIATION_HISTORIES mah
               ON mah.MEMBER_ID = s.INFLOW_MEMBER_ID AND mah.IS_CURRENT = 1
            WHERE mah.REGION_CODE = :1
              AND TRUNC(s.INFLOW_DATE) = TO_DATE(:2, 'YYYY-MM-DD')
              AND s.DELETED_AT IS NULL
            ORDER BY mah.DISTRICT_CODE, s.INFLOW_DATE""",
        [region_code, date_str],
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


def _fetch_tm_count(client, region_code, date_str):
    rows = client.query(
        """SELECT mah.DISTRICT_CODE, COUNT(DISTINCT tl.SARANG_ID) AS TM_CNT
             FROM TM_LOGS tl
             JOIN MEMBER_AFFILIATION_HISTORIES mah
               ON mah.MEMBER_ID = tl.CALLER_MEMBER_ID AND mah.IS_CURRENT = 1
            WHERE mah.REGION_CODE = :1 AND TRUNC(tl.CREATED_AT) = TO_DATE(:2, 'YYYY-MM-DD')
            GROUP BY mah.DISTRICT_CODE""",
        [region_code, date_str],
    )
    return {r['district_code']: int(r['tm_cnt']) for r in rows}


def _build_text(region_code, date_str, regs, reports, tm_by_district):
    now = datetime.datetime.now()
    lines = [
        '➖➖➖➖➖➖➖➖➖➖', f'📢 {region_code}지역 일일보고',
        f"- {_fmt_md(date_str)} {now.strftime('%H:%M')} 기준", '',
    ]

    by_district = {}
    for r in regs:
        by_district.setdefault(r['district_code'] or '-', []).append(r)
    lines.append(f'🌱 오늘 등록 {len(regs)}명')
    if regs:
        for dc in sorted(by_district.keys()):
            names = ', '.join(f"{r['pi_name']}/{r['inflow_name']}" for r in by_district[dc])
            tm_cnt = tm_by_district.get(dc, 0)
            lines.append(f'◾️{dc}구역 ({len(by_district[dc])}명, TM {tm_cnt}건): {names}')
    lines.append('')

    talk = sum(int(r['talk_count'] or 0) for r in reports)
    dm = sum(int(r['dm_count'] or 0) for r in reports)
    qr = sum(int(r['qr_count'] or 0) for r in reports)
    intake = sum(int(r['online_intake_count'] or 0) for r in reports)
    lines.append(f'📊 오늘 활동 합계 — 톡 {talk} / DM {dm} / QR {qr} / 온라인유입 {intake}')

    final_names = [r['name'] for r in reports if r['is_final'] == '1']
    draft_names = [r['name'] for r in reports if r['is_final'] != '1']
    lines.append(f"✅ 최종보고 ({len(final_names)}명): {', '.join(final_names) or '없음'}")
    if draft_names:
        lines.append(f"📝 작성 중 ({len(draft_names)}명): {', '.join(draft_names)}")

    promo = [r['promo_list'] for r in reports if r['promo_list']]
    if promo:
        lines.append('')
        lines.append(f"📣 오늘 홍보: {' / '.join(promo)}")

    lines.append('➖➖➖➖➖➖➖➖➖➖')
    text = '\n'.join(lines)
    return text[:4000] + ('\n…' if len(text) > 4000 else '')


def _dashboard_reply_markup():
    return {'inline_keyboard': [[
        {'text': '📱 앱에서 열기', 'url': 'https://t.me/logDdochi_Bot/entry?startapp=dailyReport'},
        {'text': '🌐 브라우저', 'url': 'https://page.ddochi.cloud/#/daily-report'},
    ]]}


def _build_message(client, region_code, date_str):
    regs = _fetch_registrations(client, region_code, date_str)
    reports = _fetch_daily_reports(client, region_code, date_str)
    tm_by_district = _fetch_tm_count(client, region_code, date_str)
    return _build_text(region_code, date_str, regs, reports, tm_by_district)


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
