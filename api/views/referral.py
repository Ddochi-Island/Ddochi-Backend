# 지역원 추천 코드 API — 내 링크(앱 홈)와 PIONEER /admin용 코드→이름 해석. 설계: docs/REFERRAL_CODE.md
import json

from decouple import config
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from api.auth.gate import require_jwt
from api.util.referral import referral_code, resolve_referral_codes

EVENT_URL = 'https://pioneerhq.vercel.app/event'


@csrf_exempt
@require_jwt
def my_link(request, *args, **kwargs):
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    if not config('REFERRAL_SECRET', default=''):
        return JsonResponse({'success': False, 'message': '추천 링크가 아직 설정되지 않았어요'}, status=503)
    code = referral_code(request.user['sabun'])
    return JsonResponse({'success': True, 'code': code, 'url': f'{EVENT_URL}?ref={code}'})


@csrf_exempt
def resolve(request, *args, **kwargs):
    """PIONEER 서버(/api/event-applicants)가 서버 간으로 호출 — {codes:[...]} → {ok, members:{코드:{name, region}}}."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    key = settings.PIONEER_INTERNAL_KEY
    if not key or request.headers.get('X-Pioneer-Key') != key:
        return JsonResponse({'ok': False}, status=401)
    if not config('REFERRAL_SECRET', default=''):
        return JsonResponse({'ok': False, 'error': 'REFERRAL_SECRET not set'}, status=503)
    try:
        codes = json.loads(request.body or b'{}').get('codes') or []
    except (TypeError, ValueError, AttributeError):
        codes = []
    codes = [str(c).strip() for c in codes if isinstance(c, str)][:2000]
    return JsonResponse({'ok': True, 'members': resolve_referral_codes(codes)})
