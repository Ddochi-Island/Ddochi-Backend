"""짧카(短카) 작성 — 지역원 개인 지인 기록. 레거시 Express에 대응 라우트 없음(완전 신규)."""
import json
import re
import uuid

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from api.auth.gate import require_jwt
from api.clients.data_router import DataRouterClient

_GENDERS = {'남', '여'}
_RELIGIONS = {'무교', '기독교', '불교', '천주교', '기타'}

# 밭 관리하기 RBAC 티어 — POSITION_CODE 기준(POSITION_NAME 아님, region_clerk와
# area_secretary가 둘 다 "수서기"라 이름만으로는 구분 불가).
# 전도교관·지역총무는 POSITION_CODES상 region 스코프지만 밭 관리하기(조회·떡잎 재가)는 전 지역(2026-10-05 사용자 결정)
_TIER_GLOBAL = {'admin', 'executive', 'region_lead', 'region_general_secretary'}
_TIER_REGION = {'team_lead', 'team_evangelist', 'region_clerk', 'region_mission_clerk'}
# 지역 밭은 보지만 떡잎 재가는 못 하는 직책 — 수서기·지역전도서기(2026-10-05 사용자 결정)
_NO_SPROUT_DECIDE = {'region_clerk', 'region_mission_clerk'}
# 반장 — 자기가 맡은 반(DISTRICT_GROUPS.LEADER_MEMBER_ID)의 구역 전체. 전도팀장 아래, 구역장 위.
_TIER_GROUP = {'group_lead'}
_TIER_DISTRICT_ALL = {'area_lead'}
_TIER_DISTRICT_GENERAL = {'sub_area_lead', 'team_clerk', 'team_mission_clerk', 'area_secretary'}

# 반 떡잎 목표 — 반마다 떡잎 5개를 유지(2026-09-30 사용자 결정). 밭 관리하기 상단/일일보고 텔레그램에 표시.
GROUP_SPROUT_GOAL = 5
_SPROUT_STATUS_KO = {'pending': '떡잎 재가 대기', 'approved': '떡잎 재가 완료', 'rejected': '떡잎 반려'}

# 농부일지 필드 — 단계 판정에 쓰는 필드만(짧카 자체 필드 age/gender/phone/residence/
# school_major/environment는 list_short_cards가 이미 내려주던 걸 그대로 씀).
_JOURNAL_FIELDS = [
    'faith_status', 'relation', 'personality', 'hobby', 'has_partner', 'family_relation',
    'desired_image', 'recent_concern', 'family_atmosphere', 'human_relations',
    'note_special', 'guide_comment',
]


# 농부일지 저장 시 자를 길이 — SHORT_CARDS 컬럼 길이(sql/30 이후)와 맞춤
_JOURNAL_MAX_CHARS = {
    'GENDER': 10, 'HAS_PARTNER': 500, 'RELATION': 500, 'SCHOOL_MAJOR': 500, 'RESIDENCE': 500,
    'PERSONALITY': 1000, 'HOBBY': 1000, 'FAMILY_RELATION': 1000, 'DESIRED_IMAGE': 1000, 'RECENT_CONCERN': 1000,
    'FAMILY_ATMOSPHERE': 1000, 'HUMAN_RELATIONS': 1000, 'GUIDE_COMMENT': 1000, 'NOTE_SPECIAL': 1000, 'ENVIRONMENT': 1000,
}


def _json_body(request):
    try:
        return json.loads(request.body or b'{}')
    except (TypeError, ValueError):
        return {}


def _tier_rank(code):
    for rank, tier in enumerate((_TIER_GLOBAL, _TIER_REGION, _TIER_GROUP, _TIER_DISTRICT_ALL, _TIER_DISTRICT_GENERAL)):
        if code in tier:
            return rank
    return 99


def _caller_ctx(client, sabun):
    """대표 POSITION_CODE + 소속 지역/구역 + (반장이면) 맡은 반의 구역들.
    겸직(예: 구역장+반장)이면 가장 넓은 밭 관리하기 티어의 직책을 대표로 씀 — 예전엔 SCOPE 순으로 하나만
    골라서 같은 team 스코프끼리는 순서가 무작위였음."""
    rows = client.query(
        """SELECT mah.REGION_CODE, mah.DISTRICT_CODE, mpm.POSITION_CODE
             FROM MEMBERS m
             LEFT JOIN MEMBER_AFFILIATION_HISTORIES mah ON mah.MEMBER_ID = m.MEMBER_ID AND mah.IS_CURRENT = 1
             LEFT JOIN MEMBER_POSITION_MAPPINGS mpm ON mpm.MEMBER_ID = m.MEMBER_ID
            WHERE m.MEMBER_ID = :1""",
        [sabun],
    )
    first = rows[0] if rows else {}
    codes = [r['position_code'] for r in rows if r['position_code']]
    ctx = {
        'position_code': min(codes, key=_tier_rank) if codes else None,
        'region_code': first.get('region_code'),
        'district_code': first.get('district_code'),
        'group_districts': [],
    }
    if ctx['position_code'] in _TIER_GROUP:
        groups = client.query(
            "SELECT DISTRICT_CODES FROM DISTRICT_GROUPS WHERE LEADER_MEMBER_ID = :1 AND REGION_CODE = :2 AND DELETED_AT IS NULL",
            [sabun, ctx['region_code']],
        )
        districts = {d.strip() for g in groups for d in (g['district_codes'] or '').split(',') if d.strip()}
        if ctx['district_code']:
            districts.add(ctx['district_code'])  # 반장도 자기 구역 소속 회원
        ctx['group_districts'] = sorted(districts)
    return ctx


def _scope_sql(ctx, sabun):
    """밭 관리하기 RBAC — list_short_cards/get_short_card_journal이 공유하는
    "내가 볼 수 있는 SHORT_CARDS 범위" WHERE절. alias는 항상 sc."""
    position_code = ctx['position_code']
    if position_code in _TIER_GLOBAL:
        return '1=1', []
    if position_code in _TIER_REGION:
        return ("""sc.MEMBER_ID IN (SELECT MEMBER_ID FROM MEMBER_AFFILIATION_HISTORIES
                     WHERE REGION_CODE = :1 AND IS_CURRENT = 1)""", [ctx['region_code']])
    if position_code in _TIER_GROUP:
        districts = ctx['group_districts'] or ['__none__']
        marks = ', '.join(f':{i + 2}' for i in range(len(districts)))
        return (f"""sc.MEMBER_ID IN (SELECT MEMBER_ID FROM MEMBER_AFFILIATION_HISTORIES
                     WHERE REGION_CODE = :1 AND DISTRICT_CODE IN ({marks}) AND IS_CURRENT = 1)""",
                [ctx['region_code'], *districts])
    if position_code in _TIER_DISTRICT_ALL:
        # DISTRICT_CODE는 지역마다 독립적으로 매겨져서(1~7이 전 지역에서 다 재사용됨)
        # REGION_CODE를 같이 안 걸면 다른 지역의 같은 번호 구역이 섞여 보임 —
        # 2026-09-25 실사용자 신고로 발견.
        return ("""sc.MEMBER_ID IN (SELECT MEMBER_ID FROM MEMBER_AFFILIATION_HISTORIES
                     WHERE REGION_CODE = :1 AND DISTRICT_CODE = :2 AND IS_CURRENT = 1)""",
                [ctx['region_code'], ctx['district_code']])
    if position_code in _TIER_DISTRICT_GENERAL:
        return ("""(sc.MEMBER_ID = :1 OR sc.MEMBER_ID IN (
                     SELECT mah.MEMBER_ID FROM MEMBER_AFFILIATION_HISTORIES mah
                       JOIN MEMBER_POSITION_MAPPINGS mpm ON mpm.MEMBER_ID = mah.MEMBER_ID AND mpm.POSITION_CODE = 'general'
                    WHERE mah.REGION_CODE = :2 AND mah.DISTRICT_CODE = :3 AND mah.IS_CURRENT = 1))""",
                [sabun, ctx['region_code'], ctx['district_code']])
    return 'sc.MEMBER_ID = :1', [sabun]


def _stage3_complete(row):
    s1 = all(row.get(k) for k in ('gender', 'age', 'relation', 'phone', 'residence'))
    s2 = s1 and all(row.get(k) for k in ('school_major', 'personality', 'hobby', 'has_partner', 'family_relation', 'environment'))
    s3 = s2 and all(row.get(k) for k in ('desired_image', 'recent_concern', 'family_atmosphere', 'human_relations'))
    return s1, s2, s3


def _journal_stage(row):
    """씨앗(기본)/새싹(2단계 완료)/떡잎(2단계 완료 + 반장 이상 재가). 2단계까지 채우면 재가 요청, 재가 전엔 새싹
    (2026-10-05 변경 — 전엔 3단계까지 다 채워야 재가 요청. 3단계는 이제 떡잎 이후에 채워가는 칸)."""
    _, s2, _ = _stage3_complete(row)
    if s2 and row.get('sprout_status') == 'approved':
        return '떡잎'
    if s2:
        return '새싹'
    return '씨앗'


def _can_decide_sprout(ctx, card_region, card_district):
    """떡잎 재가 권한 — 그 짧카(작성자 구역)가 속한 반의 반장 + 그 위 직책(같은 지역의 지역 티어, 전역)."""
    code = ctx['position_code']
    if code in _NO_SPROUT_DECIDE:
        return False
    if code in _TIER_GLOBAL:
        return True
    if card_region != ctx['region_code']:
        return False
    if code in _TIER_REGION:
        return True
    return code in _TIER_GROUP and card_district in ctx['group_districts']


def group_sprout_status(client, region_codes=None):
    """반별 떡잎 수 — [{groupId, region, name, leaderName, sprouts, goal}]. 떡잎 = 2단계 완료 + 떡잎 재가,
    작성자의 현재 구역이 그 반에 속한 짧카만 셈. region_codes가 None이면 전 지역."""
    sql = """SELECT g.GROUP_ID, g.REGION_CODE, g.GROUP_NAME, g.DISTRICT_CODES, m.NAME AS LEADER_NAME
               FROM DISTRICT_GROUPS g LEFT JOIN MEMBERS m ON m.MEMBER_ID = g.LEADER_MEMBER_ID
              WHERE g.DELETED_AT IS NULL"""
    args = []
    if region_codes is not None:
        if not region_codes:
            return []
        marks = ', '.join(f':{i + 1}' for i in range(len(region_codes)))
        sql += f' AND g.REGION_CODE IN ({marks})'
        args = list(region_codes)
    groups = client.query(sql, args)
    # 이름 숫자순(문자열 정렬은 '10반'이 '9반' 앞에 옴)
    groups.sort(key=lambda g: (g['region_code'], int(re.sub(r'\D', '', g['group_name']) or 0), g['group_name']))
    if not groups:
        return []
    cols = ', '.join(f'sc.{f.upper()}' for f in _JOURNAL_FIELDS)
    cards = client.query(
        f"""SELECT mah.REGION_CODE, mah.DISTRICT_CODE, sc.AGE, sc.GENDER, sc.PHONE, sc.RESIDENCE,
                   sc.SCHOOL_MAJOR, sc.ENVIRONMENT, sc.SPROUT_STATUS, {cols}
              FROM SHORT_CARDS sc
              JOIN MEMBER_AFFILIATION_HISTORIES mah ON mah.MEMBER_ID = sc.MEMBER_ID AND mah.IS_CURRENT = 1
             WHERE sc.DELETED_AT IS NULL AND sc.APPROVAL_STATUS = 'approved' AND sc.SPROUT_STATUS = 'approved'""",
        fetch_limit=5000,
    )
    sprouts = {}
    for c in cards:
        if _journal_stage(c) == '떡잎':
            key = (c['region_code'], c['district_code'])
            sprouts[key] = sprouts.get(key, 0) + 1
    out = []
    for g in groups:
        districts = [d for d in (g['district_codes'] or '').split(',') if d]
        out.append({
            'groupId': g['group_id'], 'region': g['region_code'], 'name': g['group_name'],
            'districts': districts,  # 밭 관리하기 상단 반 칩 → 그 반의 밭만 보기 필터용
            'leaderName': g['leader_name'], 'goal': GROUP_SPROUT_GOAL,
            'sprouts': sum(sprouts.get((g['region_code'], d), 0) for d in districts),
        })
    return out


@csrf_exempt
@require_jwt
def submit_short_card(request, *args, **kwargs):
    """짧카 제출. 번호가 겹치면(지역원 간) 제출을 막고, SARANG 쪽 중복은 안내만 함."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    data = body.get('data') or {}
    name = str(data.get('name') or '').strip()
    if not name:
        return JsonResponse({'success': False, 'message': '이름 필요'}, status=400)

    age = data.get('age')
    try:
        age = int(age) if age not in (None, '') else None
    except (TypeError, ValueError):
        age = None
    gender = str(data.get('gender') or '').strip() or None
    if gender not in _GENDERS:
        gender = None
    phone = str(data.get('phone') or '').strip() or None
    phone_normalized = re.sub(r'[^0-9]', '', phone or '') or None
    school_major = str(data.get('schoolMajor') or '').strip() or None
    environment = str(data.get('environment') or '').strip() or None
    residence = str(data.get('residence') or '').strip() or None
    religion = str(data.get('religion') or '').strip() or None
    if religion not in _RELIGIONS:
        religion = None
    recruit_note = str(data.get('recruitNote') or '').strip() or None

    sabun = request.user['sabun']  # 실제 제출자 — CREATED_BY/UPDATED_BY로 남김
    client = DataRouterClient()

    # 인도자 — 기본은 제출자 본인이지만, 명단에서 다른 사람을 고르면 그 사람 명의로 들어감
    # (짧카 소유자=MEMBER_ID가 바뀜, RBAC 스코프/농부일지 전부 이 값 기준).
    guide_name = str(data.get('guideName') or '').strip()
    guide_sabun = sabun
    if guide_name:
        guide_row = client.query_one(
            "SELECT MEMBER_ID FROM MEMBERS WHERE NAME = :1 AND DELETED_AT IS NULL FETCH FIRST 1 ROWS ONLY",
            [guide_name],
        )
        if not guide_row:
            return JsonResponse({'success': False, 'message': f'인도자 이름[{guide_name}]을 찾을 수 없어요'}, status=400)
        guide_sabun = guide_row['member_id']

    if phone_normalized:
        dup = client.query_one(
            """SELECT sc.MEMBER_ID, m.NAME FROM SHORT_CARDS sc
                 JOIN MEMBERS m ON m.MEMBER_ID = sc.MEMBER_ID
                WHERE sc.PHONE_NORMALIZED = :1 AND sc.DELETED_AT IS NULL
                FETCH FIRST 1 ROWS ONLY""",
            [phone_normalized],
        )
        if dup:
            if dup['member_id'] == guide_sabun:
                return JsonResponse({'success': False, 'message': '이미 제출한 짧카입니다'}, status=400)
            return JsonResponse({
                'success': False,
                'message': f"앗! {dup['name']}님이랑 같은 지인이신가봐요!! 이미 제출한 짧카입니다",
            }, status=400)

    short_card_id = uuid.uuid4().hex.upper()
    client.exec(
        """INSERT INTO SHORT_CARDS
             (SHORT_CARD_ID, MEMBER_ID, NAME, AGE, GENDER, PHONE, PHONE_NORMALIZED,
              SCHOOL_MAJOR, ENVIRONMENT, RESIDENCE, RELIGION, RECRUIT_NOTE, APPROVAL_STATUS, CREATED_BY, UPDATED_BY)
           VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9, :10, :11, :12, 'approved', :13, :13)""",
        [short_card_id, guide_sabun, name, age, gender, phone, phone_normalized,
         school_major, environment, residence, religion, recruit_note, sabun],
    )

    sarang_dup = None
    if phone_normalized:
        sarang_dup = client.query_one(
            "SELECT 1 FROM SARANG_PERSONAL_INFO WHERE PHONE_NORMALIZED = :1 FETCH FIRST 1 ROWS ONLY",
            [phone_normalized],
        )
    return JsonResponse({'success': True, 'message': '짧카 작성 완료!', 'duplicateInSarang': bool(sarang_dup)})


@csrf_exempt
@require_jwt
def list_short_cards(request, *args, **kwargs):
    """밭 관리하기 — 직책별 RBAC로 범위를 좁혀서 짧카 목록 + (반장 이상) 반별 떡잎 목표 현황."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    sabun = request.user['sabun']
    client = DataRouterClient()

    ctx = _caller_ctx(client, sabun)
    position_code = ctx['position_code']
    scope_sql, scope_args = _scope_sql(ctx, sabun)

    journal_cols = ', '.join(f'sc.{f.upper()}' for f in _JOURNAL_FIELDS)
    rows = client.query(
        f"""SELECT sc.SHORT_CARD_ID, sc.NAME, sc.AGE, sc.GENDER, sc.PHONE, sc.SCHOOL_MAJOR,
                   sc.ENVIRONMENT, sc.RESIDENCE, sc.RELIGION, sc.RECRUIT_NOTE, sc.CREATED_AT,
                   sc.APPROVAL_STATUS, sc.SPROUT_STATUS, sc.MEMBER_ID, m.NAME AS AUTHOR_NAME,
                   mah.REGION_CODE AS AUTHOR_REGION, mah.DISTRICT_CODE AS AUTHOR_DISTRICT, {journal_cols}
              FROM SHORT_CARDS sc
              JOIN MEMBERS m ON m.MEMBER_ID = sc.MEMBER_ID
              LEFT JOIN MEMBER_AFFILIATION_HISTORIES mah ON mah.MEMBER_ID = sc.MEMBER_ID AND mah.IS_CURRENT = 1
             WHERE sc.DELETED_AT IS NULL AND sc.APPROVAL_STATUS = 'approved' AND {scope_sql}
             ORDER BY sc.CREATED_AT DESC""",
        scope_args,
    )
    for r in rows:
        r['stage'] = _journal_stage(r)
        r['sprout_status_label'] = _SPROUT_STATUS_KO.get(r['sprout_status'])
        r['can_decide_sprout'] = (r['sprout_status'] == 'pending'
                                  and _can_decide_sprout(ctx, r['author_region'], r['author_district']))

    if position_code in _TIER_GLOBAL:
        others_label = '전체의 밭'
        goals = group_sprout_status(client)
    elif position_code in _TIER_REGION:
        others_label = '지역의 밭'
        goals = group_sprout_status(client, [ctx['region_code']])
    elif position_code in _TIER_GROUP:
        others_label = '반의 밭'
        goals = [g for g in group_sprout_status(client, [ctx['region_code']])
                 if g['groupId'] in _led_group_ids(client, sabun)]
    elif position_code in _TIER_DISTRICT_ALL or position_code in _TIER_DISTRICT_GENERAL:
        others_label = '구역의 밭'
        goals = []
    else:
        others_label = None  # 회원 등 본인만 보이는 티어 — "남의 밭" 자체가 없음
        goals = []

    return JsonResponse({'success': True, 'list': rows, 'othersLabel': others_label, 'groupGoals': goals})


def _led_group_ids(client, sabun):
    return {r['group_id'] for r in client.query(
        "SELECT GROUP_ID FROM DISTRICT_GROUPS WHERE LEADER_MEMBER_ID = :1 AND DELETED_AT IS NULL", [sabun])}


@csrf_exempt
@require_jwt
def decide_sprout(request, *args, **kwargs):
    """떡잎 재가/반려 — 2단계까지 채워 재가 대기(SPROUT_STATUS='pending')인 짧카만, 그 반의 반장 이상."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    short_card_id = str(body.get('shortCardId') or '').strip()
    enum_val = {'재가': 'approved', '반려': 'rejected'}.get(str(body.get('status') or '').strip())
    if not short_card_id or not enum_val:
        return JsonResponse({'success': False, 'message': 'shortCardId, status 필요'}, status=400)

    sabun = request.user['sabun']
    client = DataRouterClient()
    card = client.query_one(
        """SELECT sc.NAME, sc.SPROUT_STATUS, mah.REGION_CODE, mah.DISTRICT_CODE
             FROM SHORT_CARDS sc
             LEFT JOIN MEMBER_AFFILIATION_HISTORIES mah ON mah.MEMBER_ID = sc.MEMBER_ID AND mah.IS_CURRENT = 1
            WHERE sc.SHORT_CARD_ID = :1 AND sc.DELETED_AT IS NULL""",
        [short_card_id],
    )
    if not card:
        return JsonResponse({'success': False, 'message': '짧카를 찾을 수 없어요'}, status=404)
    if card['sprout_status'] != 'pending':
        return JsonResponse({'success': False, 'message': '떡잎 재가 대기 중인 짧카가 아니에요'}, status=400)
    if not _can_decide_sprout(_caller_ctx(client, sabun), card['region_code'], card['district_code']):
        return JsonResponse({'success': False, 'message': '그 반의 반장 이상만 떡잎 재가를 할 수 있어요'}, status=403)

    client.exec(
        """UPDATE SHORT_CARDS SET SPROUT_STATUS = :1, SPROUT_DECIDED_BY = :2, SPROUT_DECIDED_AT = SYSTIMESTAMP,
                  UPDATED_BY = :3 WHERE SHORT_CARD_ID = :4""",
        [enum_val, sabun, sabun, short_card_id],
    )
    msg = f"🍀 {card['name']} 떡잎이 됐어요!" if enum_val == 'approved' else f"{card['name']} 떡잎 재가를 반려했어요"
    return JsonResponse({'success': True, 'message': msg})


@csrf_exempt
@require_jwt
def get_short_card_journal(request, *args, **kwargs):
    """농부일지 상세 조회 — list_short_cards와 같은 RBAC 범위 밖이면 403."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    short_card_id = str(body.get('shortCardId') or '').strip()
    if not short_card_id:
        return JsonResponse({'success': False, 'message': 'shortCardId 필요'}, status=400)

    sabun = request.user['sabun']
    client = DataRouterClient()
    ctx = _caller_ctx(client, sabun)

    journal_cols = ', '.join(f'sc.{f.upper()}' for f in _JOURNAL_FIELDS)
    row = client.query_one(
        f"""SELECT sc.SHORT_CARD_ID, sc.MEMBER_ID, sc.NAME, sc.AGE, sc.GENDER, sc.PHONE,
                   sc.SCHOOL_MAJOR, sc.ENVIRONMENT, sc.RESIDENCE, sc.RELIGION, sc.RECRUIT_NOTE,
                   sc.APPROVAL_STATUS, sc.SPROUT_STATUS, m.NAME AS AUTHOR_NAME, mah.REGION_CODE, mah.DISTRICT_CODE,
                   {journal_cols}
              FROM SHORT_CARDS sc
              JOIN MEMBERS m ON m.MEMBER_ID = sc.MEMBER_ID
              LEFT JOIN MEMBER_AFFILIATION_HISTORIES mah ON mah.MEMBER_ID = sc.MEMBER_ID AND mah.IS_CURRENT = 1
             WHERE sc.SHORT_CARD_ID = :1 AND sc.DELETED_AT IS NULL""",
        [short_card_id],
    )
    if not row:
        return JsonResponse({'success': False, 'message': '짧카를 찾을 수 없어요'}, status=404)

    is_author = row['member_id'] == sabun
    position_code = ctx['position_code']
    if is_author or position_code in _TIER_GLOBAL:
        in_scope = True
    elif position_code in _TIER_REGION:
        in_scope = row['region_code'] == ctx['region_code']
    elif position_code in _TIER_GROUP:
        in_scope = row['region_code'] == ctx['region_code'] and row['district_code'] in ctx['group_districts']
    elif position_code in _TIER_DISTRICT_ALL:
        # DISTRICT_CODE는 지역마다 독립적으로 매겨짐(1~7이 전 지역에서 재사용) —
        # REGION_CODE도 같이 맞아야 진짜 같은 구역(_scope_sql과 동일 이유로 수정).
        in_scope = row['region_code'] == ctx['region_code'] and row['district_code'] == ctx['district_code']
    elif position_code in _TIER_DISTRICT_GENERAL:
        in_scope = False
        if row['region_code'] == ctx['region_code'] and row['district_code'] == ctx['district_code']:
            author_general = client.query_one(
                "SELECT 1 FROM MEMBER_POSITION_MAPPINGS WHERE MEMBER_ID = :1 AND POSITION_CODE = 'general'",
                [row['member_id']],
            )
            in_scope = bool(author_general)
    else:
        in_scope = False

    if not in_scope:
        return JsonResponse({'success': False, 'message': '볼 수 없는 짧카예요'}, status=403)

    row['stage'] = _journal_stage(row)
    row['sprout_status_label'] = _SPROUT_STATUS_KO.get(row['sprout_status'])
    row['is_editable'] = is_author
    return JsonResponse({'success': True, 'card': row})


@csrf_exempt
@require_jwt
def save_short_card_journal(request, *args, **kwargs):
    """농부일지 저장 — 인도자 본인만. 넘어온 필드만 부분 UPDATE."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    short_card_id = str(body.get('shortCardId') or '').strip()
    if not short_card_id:
        return JsonResponse({'success': False, 'message': 'shortCardId 필요'}, status=400)

    sabun = request.user['sabun']
    client = DataRouterClient()

    card = client.query_one(
        "SELECT MEMBER_ID FROM SHORT_CARDS WHERE SHORT_CARD_ID = :1 AND DELETED_AT IS NULL",
        [short_card_id],
    )
    if not card:
        return JsonResponse({'success': False, 'message': '짧카를 찾을 수 없어요'}, status=404)
    if card['member_id'] != sabun:
        return JsonResponse({'success': False, 'message': '인도자 본인만 농부일지를 쓸 수 있어요'}, status=403)

    field_map = {
        'faithStatus': 'FAITH_STATUS', 'relation': 'RELATION', 'personality': 'PERSONALITY',
        'hobby': 'HOBBY', 'hasPartner': 'HAS_PARTNER', 'familyRelation': 'FAMILY_RELATION',
        'desiredImage': 'DESIRED_IMAGE', 'recentConcern': 'RECENT_CONCERN',
        'familyAtmosphere': 'FAMILY_ATMOSPHERE', 'humanRelations': 'HUMAN_RELATIONS',
        'noteSpecial': 'NOTE_SPECIAL', 'guideComment': 'GUIDE_COMMENT',
        # 짧카 시절 값도 이어서 갱신 가능(연락처/거주지 등 — 1/2단계 필드로 재사용).
        'residence': 'RESIDENCE', 'schoolMajor': 'SCHOOL_MAJOR',
        'environment': 'ENVIRONMENT', 'age': 'AGE', 'gender': 'GENDER',
    }
    data = body.get('data') or {}
    sets, args_ = [], []
    n = 1
    for key, col in field_map.items():
        if key not in data:
            continue
        val = data[key]
        val = str(val).strip() or None if val is not None else None
        if val and col == 'AGE':
            val = re.sub(r'\D', '', val)[:3] or None  # NUMBER 컬럼 — '22살'도 저장되게
        elif val and col in _JOURNAL_MAX_CHARS:
            val = val[:_JOURNAL_MAX_CHARS[col]]  # 칸 길이 넘으면 ORA-12899로 저장 전체가 실패했음 — 넘는 부분만 자름
        sets.append(f'{col} = :{n}')
        args_.append(val)
        n += 1
    if 'phone' in data:
        phone = str(data['phone'] or '').strip() or None
        sets.append(f'PHONE = :{n}')
        args_.append(phone)
        n += 1
        sets.append(f'PHONE_NORMALIZED = :{n}')
        args_.append(re.sub(r'[^0-9]', '', phone or '') or None)
        n += 1
    if not sets:
        return JsonResponse({'success': False, 'message': '변경할 값이 없어요'}, status=400)
    sets.append(f'UPDATED_BY = :{n}')
    args_.append(sabun)
    n += 1
    args_.append(short_card_id)

    client.exec(f"UPDATE SHORT_CARDS SET {', '.join(sets)} WHERE SHORT_CARD_ID = :{n}", args_)

    # 2단계까지 다 채우면 떡잎 재가 요청(대기), 반려됐던 건 다시 채워 저장하면 재요청. 이미 떡잎이면 그대로.
    cols = ', '.join(f.upper() for f in _JOURNAL_FIELDS)
    cur = client.query_one(
        f"""SELECT AGE, GENDER, PHONE, RESIDENCE, SCHOOL_MAJOR, ENVIRONMENT, SPROUT_STATUS, {cols}
              FROM SHORT_CARDS WHERE SHORT_CARD_ID = :1""",
        [short_card_id],
    )
    _, s2, _ = _stage3_complete(cur)
    sprout = cur['sprout_status']
    if s2 and sprout in (None, 'rejected'):
        client.exec(
            "UPDATE SHORT_CARDS SET SPROUT_STATUS = 'pending', SPROUT_DECIDED_BY = NULL, SPROUT_DECIDED_AT = NULL WHERE SHORT_CARD_ID = :1",
            [short_card_id],
        )
        return JsonResponse({'success': True, 'sproutRequested': True,
                             'message': '2단계까지 다 썼어요! 반장님이 재가하면 떡잎이 돼요 🍀'})
    if not s2 and sprout == 'pending':
        client.exec("UPDATE SHORT_CARDS SET SPROUT_STATUS = NULL WHERE SHORT_CARD_ID = :1", [short_card_id])
    return JsonResponse({'success': True, 'message': '농부일지 저장했어요!'})
