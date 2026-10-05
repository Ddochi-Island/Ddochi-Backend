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


def _dots(cur, goal):
    return '●' * min(cur, goal) + '○' * max(goal - cur, 0)


def _sample_cards():
    """모양 확인용 가짜 떡잎(실DB에 안 넣음) — 실제 반 구조 위에 지역마다 다른 개수로 깔아봄."""
    full = {f: 'x' for f in ('age', 'gender', 'phone', 'residence', 'school_major', 'environment', *_JOURNAL_FIELDS)}
    spec = [('1', '1', 2), ('1', '4', 1), ('1', '6', 2), ('2', '3', 1), ('3', '4', 3), ('3', '1', 1),
            ('5', '2', 5), ('6', '7', 1)]
    cards = [{**full, 'region_code': r, 'district_code': d, 'name': f'예시{r}{d}{i}', 'author_name': '인도자',
              'sprout_status': 'approved'} for r, d, n in spec for i in range(n)]
    cards += [{**full, 'region_code': r, 'district_code': '1', 'name': 'x', 'author_name': 'y', 'sprout_status': 'pending'}
              for r in ('2', '3', '3')]
    return cards


def build_text(client, sample=False):
    groups, cards = _fetch(client)
    if sample:
        cards = _sample_cards()
    sprouts = [c for c in cards if _journal_stage(c) == '떡잎']
    pending = [c for c in cards if c['sprout_status'] == 'pending']

    by_region = {}
    for g in groups:
        by_region.setdefault(g['region_code'], []).append(g)

    now = timezone.localtime()
    total_goal = GROUP_SPROUT_GOAL * len(groups)
    pct = round(100 * len(sprouts) / total_goal) if total_goal else 0
    lines = [
        '🍀 <b>수지역 떡잎 전광판</b>' + (' <i>(예시 데이터)</i>' if sample else ''),
        f'<i>{now.month:02d}/{now.day:02d}({_WEEK[now.weekday()]}) {now:%H:%M} 기준</i>',
        '',
        f'<b>전체 {len(sprouts)} / {total_goal}</b>  ·  {pct}%',
    ]
    # 지역마다: 머리줄(합계·재가 대기) / 반 게이지 / 떡잎 있는 구역만 — 0인 구역까지 다 늘어놓으면 숫자에 묻혀 안 읽혔음
    for region, gs in by_region.items():
        mine = [c for c in sprouts if c['region_code'] == region]
        waiting = sum(1 for c in pending if c['region_code'] == region)
        head = f'\n<b>{region}지역</b>  {len(mine)}/{GROUP_SPROUT_GOAL * len(gs)}'
        if waiting:
            head += f'  ⏳ 대기 {waiting}'
        lines.append(head)
        parts = []
        for g in gs:
            ds = (g['district_codes'] or '').split(',')
            cnt = sum(1 for c in mine if c['district_code'] in ds)
            parts.append(f"{html.escape(g['group_name'])} {_dots(cnt, GROUP_SPROUT_GOAL)}{'✅' if cnt >= GROUP_SPROUT_GOAL else ''}")
        lines.append('   '.join(parts))
        counts = {}
        for c in mine:
            counts[c['district_code']] = counts.get(c['district_code'], 0) + 1
        if counts:
            lines.append('<i>' + ' · '.join(f'{d}구역 {n}' for d, n in sorted(counts.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else 99)) + '</i>')

    # 지인/인도자 명단은 맨 아래 한 박스에 모아 접어둠
    if sprouts:
        rows = []
        for region in by_region:
            mine = sorted((c for c in sprouts if c['region_code'] == region), key=lambda c: c['district_code'] or '')
            if mine:
                rows.append(f'<b>{region}지역</b>')
                rows += [f"🍀 {html.escape(c['name'] or '-')} / <i>{html.escape(c['author_name'] or '-')}</i>  ({c['district_code']}구역)" for c in mine]
        lines += ['', '<b>🍀 떡잎 명단</b>', '<blockquote expandable>' + '\n'.join(rows) + '</blockquote>']
    return '\n'.join(lines)


_MARKUP = {'inline_keyboard': [[{'text': '🏞️ 밭 관리하기에서 보기', 'url': 'https://page.ddochi.cloud/#/shortCardList'}]]}


def send_sprout_board(client, sample=False):
    cfg = load_team_config(client, TEAM_ID)
    chat_id = cfg.get('matchingChatId')
    if not chat_id:
        return {'skipped': True, 'reason': 'no_chat_id'}
    return send_fresh_dashboard(
        client, TEAM_ID, chat_id, build_text(client, sample), _MARKUP, cfg,
        'lastSproutBoardMsgId', 'lastSproutBoardMsgDate', 'sprout_board',
    )
