# 수지역 떡잎 전광판 — 매일 22시 수지역장·전도교관·지역총무용으로 지역별/반별 떡잎 수와 지인/인도자 명단을 보냄
import html

from django.utils import timezone

from api.telegram.dashboard_send import send_fresh_dashboard
from api.telegram.team_config import load_team_config
from api.views.short_card import GROUP_SPROUT_GOAL, _JOURNAL_FIELDS, _journal_stage

TEAM_ID = '수지역'  # 수지역 매칭현황판과 같은 방("[대학] 전도시스템", matchingChatId)
_WEEK = ['월', '화', '수', '목', '금', '토', '일']


def _fetch(client):
    groups = client.query(
        """SELECT REGION_CODE, GROUP_NAME, DISTRICT_CODES FROM DISTRICT_GROUPS
            WHERE DELETED_AT IS NULL ORDER BY REGION_CODE, GROUP_NAME"""
    )
    cols = ', '.join(f'sc.{f.upper()}' for f in _JOURNAL_FIELDS)
    cards = client.query(
        f"""SELECT mah.REGION_CODE, mah.DISTRICT_CODE, sc.NAME, am.NAME AS AUTHOR_NAME,
                   sc.AGE, sc.GENDER, sc.PHONE, sc.RESIDENCE, sc.SCHOOL_MAJOR, sc.ENVIRONMENT, sc.SPROUT_STATUS, {cols}
              FROM SHORT_CARDS sc
              JOIN MEMBERS am ON am.MEMBER_ID = sc.MEMBER_ID
              JOIN MEMBER_AFFILIATION_HISTORIES mah ON mah.MEMBER_ID = sc.MEMBER_ID AND mah.IS_CURRENT = 1
             WHERE sc.DELETED_AT IS NULL AND sc.APPROVAL_STATUS = 'approved' AND sc.SPROUT_STATUS IN ('approved', 'pending')""",
        fetch_limit=5000,
    )
    return groups, cards


def _bar(cur, goal, cells=10):
    filled = min(cells, round(cells * cur / goal)) if goal else 0
    return '■' * filled + '□' * (cells - filled)


def build_text(client):
    groups, cards = _fetch(client)
    sprouts = [c for c in cards if _journal_stage(c) == '떡잎']
    pending = [c for c in cards if c['sprout_status'] == 'pending']

    by_region = {}
    for g in groups:
        by_region.setdefault(g['region_code'], []).append(g)

    now = timezone.localtime()
    total_goal = GROUP_SPROUT_GOAL * len(groups)
    lines = [
        '🍀 <b>수지역 떡잎 전광판</b>',
        f'<i>{now.month:02d}/{now.day:02d}({_WEEK[now.weekday()]}) {now:%H:%M} 기준</i>',
        '',
        f'<b>전체 {len(sprouts)} / {total_goal}</b>  <code>{_bar(len(sprouts), total_goal)}</code> '
        f'{round(100 * len(sprouts) / total_goal) if total_goal else 0}%',
        '',
    ]
    for region, gs in by_region.items():
        mine = [c for c in sprouts if c['region_code'] == region]
        waiting = sum(1 for c in pending if c['region_code'] == region)
        head = f'<b>{region}지역</b>  <code>{len(mine)}/{GROUP_SPROUT_GOAL * len(gs)}</code>'
        if waiting:
            head += f'  ⏳ 재가 대기 {waiting}건'
        lines.append(head)
        if mine:
            names = '\n'.join(f"🍀 {html.escape(c['name'] or '-')} / <i>{html.escape(c['author_name'] or '-')}</i>" for c in mine)
            lines.append(f'<blockquote expandable>{names}</blockquote>')

    # 반별 떡잎 표 — 작성자의 현재 구역이 반에 속한 떡잎 수
    names = sorted({g['group_name'] for g in groups})
    lines += ['', '<b>📊 반별 떡잎</b>']
    # 고정폭 글꼴에서 한글은 2칸이라 'N지역  '(7칸)에 맞춰 머리줄 앞을 7칸 비움
    table = ['       ' + ''.join(f'{n:<6}' for n in names).rstrip()]
    for region, gs in by_region.items():
        cells = []
        for n in names:
            g = next((x for x in gs if x['group_name'] == n), None)
            if not g:
                cells.append(f"{'-':<6}")
                continue
            ds = (g['district_codes'] or '').split(',')
            cnt = sum(1 for c in sprouts if c['region_code'] == region and c['district_code'] in ds)
            cells.append(f'{cnt}/{GROUP_SPROUT_GOAL}{"✅" if cnt >= GROUP_SPROUT_GOAL else ""}'.ljust(6))
        table.append((f'{region}지역  ' + ''.join(cells)).rstrip())
    lines.append('<pre>' + html.escape('\n'.join(table)) + '</pre>')
    lines.append('<a href="https://page.ddochi.cloud/#/shortCardList">🏞️ 밭 관리하기에서 보기</a>')
    return '\n'.join(lines)


def send_sprout_board(client):
    cfg = load_team_config(client, TEAM_ID)
    chat_id = cfg.get('matchingChatId')
    if not chat_id:
        return {'skipped': True, 'reason': 'no_chat_id'}
    return send_fresh_dashboard(
        client, TEAM_ID, chat_id, build_text(client), {'inline_keyboard': []}, cfg,
        'lastSproutBoardMsgId', 'lastSproutBoardMsgDate', 'sprout_board',
    )
