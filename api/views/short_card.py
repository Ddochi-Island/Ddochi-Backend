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


def _json_body(request):
    try:
        return json.loads(request.body or b'{}')
    except (TypeError, ValueError):
        return {}


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

    sabun = request.user['sabun']
    client = DataRouterClient()

    if phone_normalized:
        dup = client.query_one(
            """SELECT sc.MEMBER_ID, m.NAME FROM SHORT_CARDS sc
                 JOIN MEMBERS m ON m.MEMBER_ID = sc.MEMBER_ID
                WHERE sc.PHONE_NORMALIZED = :1 AND sc.DELETED_AT IS NULL
                FETCH FIRST 1 ROWS ONLY""",
            [phone_normalized],
        )
        if dup:
            if dup['member_id'] == sabun:
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
        [short_card_id, sabun, name, age, gender, phone, phone_normalized,
         school_major, environment, residence, religion, recruit_note, sabun],
    )

    sarang_dup = None
    if phone_normalized:
        sarang_dup = client.query_one(
            "SELECT 1 FROM SARANG_PERSONAL_INFO WHERE PHONE_NORMALIZED = :1 FETCH FIRST 1 ROWS ONLY",
            [phone_normalized],
        )
    return JsonResponse({'success': True, 'message': '짧카 작성 완료!', 'duplicateInSarang': bool(sarang_dup)})
