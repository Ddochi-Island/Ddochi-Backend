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
    districts = client.query(
        """SELECT DISTINCT REGION_CODE, DISTRICT_CODE FROM MEMBER_AFFILIATION_HISTORIES
            WHERE IS_CURRENT = 1 AND DISTRICT_CODE IS NOT NULL"""
    )
    return groups, cards, districts


def _bar(cur, goal, cells=10):
    filled = min(cells, round(cells * cur / goal)) if goal else 0
    return '■' * filled + '□' * (cells - filled)


def _dots(cur, goal):
    return '●' * min(cur, goal) + '○' * max(goal - cur, 0)


def build_text(client):
    groups, cards, districts = _fetch(client)
    sprouts = [c for c in cards if _journal_stage(c) == '떡잎']
    pending = [c for c in cards if c['sprout_status'] == 'pending']

    by_region = {}
    for g in groups:
        by_region.setdefault(g['region_code'], []).append(g)
    region_districts = {}
    for d in districts:
        region_districts.setdefault(d['region_code'], set()).add(d['district_code'])

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
        head = f'<b>{region}지역</b>  {len(mine)}/{GROUP_SPROUT_GOAL * len(gs)}'
        if waiting:
            head += f'  ⏳ 재가 대기 {waiting}건'
        lines.append(head)
        # 구역별 떡잎 수 — 한 줄에 4개씩, 떡잎 있는 구역은 굵게
        cells = []
        for d in sorted(region_districts.get(region, ()), key=lambda x: int(x) if x.isdigit() else 99):
            n = sum(1 for c in mine if c['district_code'] == d)
            cells.append(f'{d}구역 <b>{n}</b>' if n else f'{d}구역 0')
        rows = [' · '.join(cells[i:i + 4]) for i in range(0, len(cells), 4)]
        if mine:
            names = '\n'.join(
                f"{c['district_code']}구역  🍀 {html.escape(c['name'] or '-')} / <i>{html.escape(c['author_name'] or '-')}</i>"
                for c in sorted(mine, key=lambda c: c['district_code'] or ''))
            rows += ['', names]
        lines.append(f"<blockquote{' expandable' if mine else ''}>" + '\n'.join(rows) + '</blockquote>')

    # 반별 떡잎 — 목표 5칸 점(●채움/○빈칸). 고정폭 표(<pre>)는 텔레그램이 코드 박스로 감싸 읽기 불편했음
    lines.append('<b>📊 반별 떡잎</b>')
    rows = []
    for region, gs in by_region.items():
        parts = []
        for g in gs:
            ds = (g['district_codes'] or '').split(',')
            cnt = sum(1 for c in sprouts if c['region_code'] == region and c['district_code'] in ds)
            parts.append(f"{html.escape(g['group_name'])} {_dots(cnt, GROUP_SPROUT_GOAL)}{' ✅' if cnt >= GROUP_SPROUT_GOAL else ''}")
        rows.append(f'<b>{region}지역</b>  ' + '   '.join(parts))
    lines.append('<blockquote>' + '\n'.join(rows) + '</blockquote>')
    return '\n'.join(lines)


_MARKUP = {'inline_keyboard': [[{'text': '🏞️ 밭 관리하기에서 보기', 'url': 'https://page.ddochi.cloud/#/shortCardList'}]]}


def send_sprout_board(client):
    cfg = load_team_config(client, TEAM_ID)
    chat_id = cfg.get('matchingChatId')
    if not chat_id:
        return {'skipped': True, 'reason': 'no_chat_id'}
    return send_fresh_dashboard(
        client, TEAM_ID, chat_id, build_text(client), _MARKUP, cfg,
        'lastSproutBoardMsgId', 'lastSproutBoardMsgDate', 'sprout_board',
    )
