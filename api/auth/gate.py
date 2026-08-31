# middleware.js(apiAuth) 포팅 — Bearer JWT 검증 후 request.user 세팅.
import functools

from django.http import JsonResponse

from api.auth import jwt as auth_jwt
from api.clients.data_router import DataRouterClient

# 쿼리 파라미터/쿠키 폴백은 <img>/<a download> 대응용인데 이번 포팅 범위 endpoint는
# 전부 fetch(JSON) 호출이라 Authorization 헤더만 지원. 필요해지면 추가.
def _read_bearer(request):
    auth = request.META.get('HTTP_AUTHORIZATION', '')
    if auth.startswith('Bearer '):
        return auth[len('Bearer '):].strip()
    return ''


def require_jwt(view_func):
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        token = _read_bearer(request)
        if not token:
            return JsonResponse({'error': 'missing_token'}, status=401)
        try:
            decoded = auth_jwt.verify(token, expected_typ='access')
        except Exception as e:
            return JsonResponse({'error': 'invalid_token', 'code': type(e).__name__}, status=401)
        request.user = decoded
        return view_func(request, *args, **kwargs)

    return wrapper


def get_author_context(sabun):
    """assets.js:681 getAuthorContext 포팅 — 없으면 sabun/'0'/'0' 폴백."""
    u = DataRouterClient().query_one(
        'SELECT NAME, TEAM_ID, AREA_ID FROM USERS WHERE SABUN = :1',
        [sabun],
    )
    return {
        'sabun': sabun,
        'name': (u or {}).get('name') or sabun,
        'team_id': (u or {}).get('team_id') or '0',
        'area_id': (u or {}).get('area_id') or '0',
    }
