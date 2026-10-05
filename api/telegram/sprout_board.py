# 수지역 떡잎 전광판 — 매일 22시 수지역장·전도교관·지역총무용으로 지역별/반별/구역별 떡잎 수와 지인/인도자 명단을 보냄
# 텔레그램 리치 메시지(sendRichMessage, Bot API 10.1 블록: 제목/표/접이식) — 레거시 주간 점수판과 같은 방식.
from django.utils import timezone

from api.telegram.dashboard_send import send_fresh_dashboard
from api.telegram.team_config import load_team_config
from api.views.short_card import GROUP_SPROUT_GOAL, _JOURNAL_FIELDS, _journal_stage

TEAM_ID = '수지역'  # 수지역 매칭현황판과 같은 방("[대학] 전도시스템", matchingChatId)
_WEEK = ['월', '화', '수', '목', '금', '토', '일']
_MARKUP = {'inline_keyboard': [[{'text': '🏞️ 밭 관리하기에서 보기', 'url': 'https://page.ddochi.cloud/#/shortCardList'}]]}


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
        """SELECT DISTINCT mah.REGION_CODE, mah.DISTRICT_CODE FROM MEMBER_AFFILIATION_HISTORIES mah
             JOIN MEMBERS m ON m.MEMBER_ID = mah.MEMBER_ID AND m.STATUS = 'ACTIVE' AND m.DELETED_AT IS NULL
            WHERE mah.IS_CURRENT = 1 AND mah.DISTRICT_CODE IS NOT NULL"""
    )
    return groups, cards, districts


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


def _cell(text, bold=False):
    return {'text': {'type': 'bold', 'text': text} if bold else text, 'align': 'center', 'valign': 'middle'}


def _num_key(v):
    return int(v) if str(v).isdigit() else 99


def build_blocks(client, sample=False):
    groups, cards, districts = _fetch(client)
    if sample:
        cards = _sample_cards()
    sprouts = [c for c in cards if _journal_stage(c) == '떡잎']
    pending = [c for c in cards if c['sprout_status'] == 'pending']

    by_region = {}
    for g in groups:
        by_region.setdefault(g['region_code'], []).append(g)
    region_districts = {}
    for d in districts:
        if d['region_code'] in by_region:
            region_districts.setdefault(d['region_code'], set()).add(d['district_code'])
    # 반 이름은 지역마다 다름(예: 5지역 9반·10반) — 지역 안에서 이름의 숫자순(문자열 정렬은 10반이 9반 앞에 옴)
    for gs in by_region.values():
        gs.sort(key=lambda g: (_num_key(''.join(ch for ch in g['group_name'] if ch.isdigit())), g['group_name']))
    width = max((len(gs) for gs in by_region.values()), default=0)

    def count(region, ds=None):
        return sum(1 for c in sprouts if c['region_code'] == region and (ds is None or c['district_code'] in ds))

    now = timezone.localtime()
    total_goal = GROUP_SPROUT_GOAL * len(groups)
    pct = round(100 * len(sprouts) / total_goal) if total_goal else 0

    # 메인 표 — 지역 × 반(n/5, 다 채우면 ✅) + 합계 + 재가 대기
    main = [[_cell('지역'), *[_cell('반') for _ in range(width)], _cell('합계'), _cell('대기')]]
    for region, gs in by_region.items():
        row = [_cell(f'{region}지역')]
        for g in gs:
            n = count(region, (g['district_codes'] or '').split(','))
            row.append(_cell(f"{g['group_name']} {n}/{GROUP_SPROUT_GOAL}{' ✅' if n >= GROUP_SPROUT_GOAL else ''}"))
        row += [_cell('') for _ in range(width - len(gs))]
        waiting = sum(1 for c in pending if c['region_code'] == region)
        row += [_cell(f'{count(region)}/{GROUP_SPROUT_GOAL * len(gs)}', bold=True), _cell(str(waiting) if waiting else '-')]
        main.append(row)
    main.append([_cell('전체', bold=True), *[_cell('') for _ in range(width)],
                 _cell(f'{len(sprouts)}/{total_goal}', bold=True), _cell(str(len(pending)) if pending else '-', bold=True)])

    # 구역별 표 — 지역 × 구역, 그 지역에 없는 구역은 빈칸
    all_d = sorted({d for ds in region_districts.values() for d in ds}, key=_num_key)
    district_table = [[_cell('지역'), *[_cell(f'{d}구역') for d in all_d], _cell('합계', bold=True)]]
    for region in by_region:
        mine = region_districts.get(region, set())
        district_table.append([_cell(f'{region}지역'),
                               *[_cell(str(count(region, [d])) if d in mine else '') for d in all_d],
                               _cell(str(count(region)), bold=True)])

    # 명단 — 지역별 접이식, 안에 구역/지인/인도자 표
    roster = []
    for region in by_region:
        mine = sorted((c for c in sprouts if c['region_code'] == region), key=lambda c: _num_key(c['district_code']))
        if mine:
            cells = [[_cell('구역'), _cell('지인'), _cell('인도자')]]
            cells += [[_cell(f"{c['district_code']}구역"), _cell(c['name'] or '-'), _cell(c['author_name'] or '-')] for c in mine]
            roster.append({'type': 'details', 'summary': f'{region}지역 ({len(mine)})', 'blocks': [{'type': 'table', 'cells': cells}]})

    title = '🍀 수지역 떡잎 전광판' + (' (예시 데이터)' if sample else '')
    blocks = [
        {'type': 'heading', 'text': title, 'size': 2},
        {'type': 'paragraph', 'text': f'전체 {len(sprouts)} / {total_goal} ({pct}%) · 반마다 떡잎 {GROUP_SPROUT_GOAL}개 유지'},
        {'type': 'details', 'summary': '📍 구역별 떡잎', 'is_open': True, 'blocks': [{'type': 'table', 'cells': district_table}]},
    ]
    if roster:
        blocks.append({'type': 'details', 'summary': '📝 떡잎 명단 (지인 / 인도자)', 'blocks': roster})
    blocks.append({'type': 'details', 'summary': '👥 반별 떡잎', 'is_open': True, 'blocks': [{'type': 'table', 'cells': main}]})
    blocks.append({'type': 'footer', 'text': {'type': 'italic',
                                              'text': f'{now.month}/{now.day}({_WEEK[now.weekday()]}) {now:%H:%M} 기준'}})
    return blocks


def send_sprout_board(client, sample=False):
    cfg = load_team_config(client, TEAM_ID)
    chat_id = cfg.get('matchingChatId')
    if not chat_id:
        return {'skipped': True, 'reason': 'no_chat_id'}
    return send_fresh_dashboard(
        client, TEAM_ID, chat_id, None, _MARKUP, cfg,
        'lastSproutBoardMsgId', 'lastSproutBoardMsgDate', 'sprout_board', rich_blocks=build_blocks(client, sample),
    )
