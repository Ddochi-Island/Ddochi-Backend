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
_TIER_GLOBAL = {'admin', 'executive'}
_TIER_REGION = {'team_lead', 'team_evangelist', 'region_lead',
                 'region_general_secretary', 'region_clerk', 'region_mission_clerk'}
_TIER_DISTRICT_ALL = {'area_lead'}
_TIER_DISTRICT_GENERAL = {'sub_area_lead', 'team_clerk', 'team_mission_clerk', 'area_secretary'}

# 짧카 재가 — 전도팀장/지역장만 (밭 관리하기 조회 RBAC의 "지역 전체" 티어보다 좁음).
_APPROVAL_TIER = {'team_evangelist', 'team_lead'}
_APPROVAL_STATUS_KO = {'pending': '대기중', 'approved': '재가완료', 'rejected': '반려됨'}

# 농부일지 필드 — 단계 판정에 쓰는 필드만(짧카 자체 필드 age/gender/phone/residence/
# school_major/environment는 list_short_cards가 이미 내려주던 걸 그대로 씀).
_JOURNAL_FIELDS = [
    'faith_status', 'relation', 'personality', 'hobby', 'has_partner', 'family_relation',
    'desired_image', 'recent_concern', 'family_atmosphere', 'human_relations',
    'note_special', 'guide_comment',
]


def _json_body(request):
    try:
        return json.loads(request.body or b'{}')
    except (TypeError, ValueError):
        return {}


def _caller_ctx(client, sabun):
    """대표 POSITION_CODE + 소속 지역/구역 — admin_users.py의 SCOPE 우선순위 조회 패턴 재사용."""
    row = client.query_one(
        """SELECT mah.REGION_CODE, mah.DISTRICT_CODE, mpm.POSITION_CODE
             FROM MEMBERS m
             LEFT JOIN MEMBER_AFFILIATION_HISTORIES mah ON mah.MEMBER_ID = m.MEMBER_ID AND mah.IS_CURRENT = 1
             LEFT JOIN MEMBER_POSITION_MAPPINGS mpm ON mpm.MEMBER_ID = m.MEMBER_ID
             LEFT JOIN POSITION_CODES pc ON pc.POSITION_CODE = mpm.POSITION_CODE
            WHERE m.MEMBER_ID = :1
            ORDER BY CASE pc.SCOPE WHEN 'global' THEN 0 WHEN 'region' THEN 1 ELSE 2 END
            FETCH FIRST 1 ROWS ONLY""",
        [sabun],
    )
    return {
        'position_code': row['position_code'] if row else None,
        'region_code': row['region_code'] if row else None,
        'district_code': row['district_code'] if row else None,
    }


def _scope_sql(ctx, sabun):
    """밭 관리하기 RBAC — list_short_cards/get_short_card_journal이 공유하는
    "내가 볼 수 있는 SHORT_CARDS 범위" WHERE절. alias는 항상 sc."""
    position_code = ctx['position_code']
    if position_code in _TIER_GLOBAL:
        return '1=1', []
    if position_code in _TIER_REGION:
        return ("""sc.MEMBER_ID IN (SELECT MEMBER_ID FROM MEMBER_AFFILIATION_HISTORIES
                     WHERE REGION_CODE = :1 AND IS_CURRENT = 1)""", [ctx['region_code']])
    if position_code in _TIER_DISTRICT_ALL:
        return ("""sc.MEMBER_ID IN (SELECT MEMBER_ID FROM MEMBER_AFFILIATION_HISTORIES
                     WHERE DISTRICT_CODE = :1 AND IS_CURRENT = 1)""", [ctx['district_code']])
    if position_code in _TIER_DISTRICT_GENERAL:
        return ("""(sc.MEMBER_ID = :1 OR sc.MEMBER_ID IN (
                     SELECT mah.MEMBER_ID FROM MEMBER_AFFILIATION_HISTORIES mah
                       JOIN MEMBER_POSITION_MAPPINGS mpm ON mpm.MEMBER_ID = mah.MEMBER_ID AND mpm.POSITION_CODE = 'general'
                    WHERE mah.DISTRICT_CODE = :2 AND mah.IS_CURRENT = 1))""", [sabun, ctx['district_code']])
    return 'sc.MEMBER_ID = :1', [sabun]


def _journal_stage(row):
    """씨앗(기본)/새싹(2단계 완료)/떡잎(3단계 완료). 사용자 확정: 1단계 다 채워지면
    씨앗, 2단계 다 채워지면 새싹, 3단계 다 채워지면 떡잎."""
    s1 = all(row.get(k) for k in ('gender', 'age', 'relation', 'phone', 'residence'))
    s2 = s1 and all(row.get(k) for k in ('school_major', 'personality', 'hobby', 'has_partner', 'family_relation', 'environment'))
    s3 = s2 and all(row.get(k) for k in ('desired_image', 'recent_concern', 'family_atmosphere', 'human_relations'))
    if s3:
        return '떡잎'
    if s2:
        return '새싹'
    return '씨앗'


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
              SCHOOL_MAJOR, ENVIRONMENT, RESIDENCE, RELIGION, RECRUIT_NOTE, CREATED_BY, UPDATED_BY)
           VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9, :10, :11, :12, :13, :13)""",
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
    """밭 관리하기 — 직책별 RBAC로 범위를 좁혀서 짧카 목록을 보여줌."""
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
                   sc.APPROVAL_STATUS, sc.MEMBER_ID, m.NAME AS AUTHOR_NAME, {journal_cols}
              FROM SHORT_CARDS sc
              JOIN MEMBERS m ON m.MEMBER_ID = sc.MEMBER_ID
             WHERE sc.DELETED_AT IS NULL AND {scope_sql}
             ORDER BY sc.CREATED_AT DESC""",
        scope_args,
    )
    for r in rows:
        r['approval_status_label'] = _APPROVAL_STATUS_KO.get(r['approval_status'], r['approval_status'])
        r['stage'] = _journal_stage(r) if r['approval_status'] == 'approved' else None
    can_approve = position_code in _APPROVAL_TIER

    if position_code in _TIER_GLOBAL:
        others_label = '전체의 밭'
    elif position_code in _TIER_REGION:
        others_label = '지역의 밭'
    elif position_code in _TIER_DISTRICT_ALL or position_code in _TIER_DISTRICT_GENERAL:
        others_label = '구역의 밭'
    else:
        others_label = None  # 회원 등 본인만 보이는 티어 — "남의 밭" 자체가 없음

    return JsonResponse({'success': True, 'list': rows, 'canApprove': can_approve, 'othersLabel': others_label})


@csrf_exempt
@require_jwt
def approve_short_card(request, *args, **kwargs):
    """짧카 재가/반려 — 전도팀장/지역장만, 그것도 같은 지역 짧카만."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    short_card_id = str(body.get('shortCardId') or '').strip()
    status_map = {'재가': 'approved', '반려': 'rejected'}
    enum_val = status_map.get(str(body.get('status') or '').strip())
    if not short_card_id or not enum_val:
        return JsonResponse({'success': False, 'message': 'shortCardId, status 필요'}, status=400)

    sabun = request.user['sabun']
    client = DataRouterClient()

    ctx = _caller_ctx(client, sabun)
    if ctx['position_code'] not in _APPROVAL_TIER:
        return JsonResponse({'success': False, 'message': '전도팀장/지역장만 재가할 수 있어요'}, status=403)

    card = client.query_one(
        "SELECT MEMBER_ID FROM SHORT_CARDS WHERE SHORT_CARD_ID = :1 AND DELETED_AT IS NULL",
        [short_card_id],
    )
    if not card:
        return JsonResponse({'success': False, 'message': '짧카를 찾을 수 없어요'}, status=404)

    author = client.query_one(
        "SELECT REGION_CODE FROM MEMBER_AFFILIATION_HISTORIES WHERE MEMBER_ID = :1 AND IS_CURRENT = 1",
        [card['member_id']],
    )
    if not author or author['region_code'] != ctx['region_code']:
        return JsonResponse({'success': False, 'message': '같은 지역의 짧카만 재가할 수 있어요'}, status=403)

    client.exec(
        "UPDATE SHORT_CARDS SET APPROVAL_STATUS = :1, UPDATED_BY = :2 WHERE SHORT_CARD_ID = :3",
        [enum_val, sabun, short_card_id],
    )
    return JsonResponse({'success': True, 'message': f"{_APPROVAL_STATUS_KO[enum_val]} 처리했어요"})


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
                   sc.APPROVAL_STATUS, m.NAME AS AUTHOR_NAME, mah.REGION_CODE, mah.DISTRICT_CODE,
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
    elif position_code in _TIER_DISTRICT_ALL:
        in_scope = row['district_code'] == ctx['district_code']
    elif position_code in _TIER_DISTRICT_GENERAL:
        in_scope = False
        if row['district_code'] == ctx['district_code']:
            author_general = client.query_one(
                "SELECT 1 FROM MEMBER_POSITION_MAPPINGS WHERE MEMBER_ID = :1 AND POSITION_CODE = 'general'",
                [row['member_id']],
            )
            in_scope = bool(author_general)
    else:
        in_scope = False

    if not in_scope:
        return JsonResponse({'success': False, 'message': '볼 수 없는 짧카예요'}, status=403)

    row['stage'] = _journal_stage(row) if row['approval_status'] == 'approved' else None
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
    return JsonResponse({'success': True, 'message': '농부일지 저장했어요!'})
