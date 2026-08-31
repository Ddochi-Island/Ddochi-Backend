"""auth.js 포팅 — login/refresh 실제 로직. admin-unlock/auth-config는 apiAuth
글로벌 JWT 게이트가 아직 없어서 스텁으로 남겨둠."""
import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from api.auth import jwt as auth_jwt
from api.auth import passkey
from api.clients.data_router import DataRouterClient, DataRouterError


# ROLES.REGION_ID/TEAMS/AREAS 없는 dev 스키마용 조정 — team/area는 TEAM_ID/AREA_ID
# 그대로 사용 (원본은 TEAMS/AREAS.DISPLAY_NAME으로 조인).
def find_user_by_sabun(sabun):
    if not sabun:
        return None
    return DataRouterClient().query_one(
        """SELECT u.SABUN, u.NAME,
                  u.TEAM_ID, u.TEAM_ID AS TEAM_NAME,
                  u.AREA_ID, u.AREA_ID AS AREA_NAME,
                  u.TELEGRAM_ID,
                  (SELECT r.NAME FROM ROLES r
                    WHERE r.DELETED_AT IS NULL
                      AND INSTR(u.ROLE_IDS, '"' || r.ROLE_ID || '"') > 0
                    ORDER BY CASE r.SCOPE WHEN 'global' THEN 0 WHEN 'region' THEN 1 ELSE 2 END
                    FETCH FIRST 1 ROWS ONLY) AS POSITION,
                  (SELECT JSON_ARRAYAGG(jt.PERM RETURNING CLOB)
                     FROM ROLES r,
                          JSON_TABLE(r.PERMISSIONS, '$[*]' COLUMNS (PERM VARCHAR2(50 CHAR) PATH '$')) jt
                    WHERE r.DELETED_AT IS NULL
                      AND INSTR(u.ROLE_IDS, '"' || r.ROLE_ID || '"') > 0) AS PERMS,
                  u.CREATED_AT AS JOINED_AT,
                  u.DELETED_AT
             FROM USERS u
            WHERE u.SABUN = :1 AND u.DELETED_AT IS NULL""",
        [sabun],
        cache_ttl_ms=1_000,
        priority='high',
    )


def list_valid_names():
    try:
        rows = DataRouterClient().query('SELECT NAME FROM USERS WHERE DELETED_AT IS NULL ORDER BY NAME')
    except DataRouterError:
        return []
    return [r['name'] for r in rows if r.get('name')]


def parse_perms(raw):
    if not raw:
        return []
    try:
        arr = json.loads(raw)
        return list(dict.fromkeys(arr)) if isinstance(arr, list) else []
    except (TypeError, ValueError):
        return []


def build_session_user(row):
    return {
        'sabun': row['sabun'],
        'name': row['name'],
        'team': row['team_name'],
        'position': row['position'],
        'area': row['area_name'] or '',
        'role': row['position'],
        'permissions': parse_perms(row['perms']),
    }


def login_response(user, tokens, valid_names=None):
    return {
        'ok': True,
        'success': True,
        **tokens,
        'user': user,
        'sabun': user['sabun'],
        'name': user['name'],
        'team': user['team'],
        'area': user.get('area') or '',
        'role': user.get('role') or user.get('position') or '',
        'validNames': valid_names or [],
    }


def _json_body(request):
    try:
        return json.loads(request.body or b'{}')
    except (TypeError, ValueError):
        return {}


@csrf_exempt
def login(request, *args, **kwargs):
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    sabun = str(body.get('sabun') or '').strip()
    supplied = body.get('passkey')
    if not sabun:
        return JsonResponse({'ok': False, 'success': False, 'error': 'sabun_required', 'message': '사번을 입력해주세요'}, status=400)

    verified, reason = passkey.verify(supplied)
    if not verified:
        return JsonResponse({
            'ok': False, 'success': False,
            'error': 'passkey_invalid', 'reason': reason,
            'message': '패스키가 올바르지 않습니다',
        }, status=401)

    row = find_user_by_sabun(sabun)
    if not row:
        return JsonResponse({
            'ok': False, 'success': False,
            'error': 'user_not_found',
            'message': '사번에 해당하는 사용자를 찾을 수 없습니다',
        }, status=404)

    try:
        session_user = build_session_user(row)
        tokens = auth_jwt.sign(session_user)
        return JsonResponse(login_response(session_user, tokens, list_valid_names()))
    except DataRouterError as e:
        return JsonResponse({'ok': False, 'success': False, 'error': e.code or 'login_failed', 'message': str(e)}, status=500)


@csrf_exempt
def refresh(request, *args, **kwargs):
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    refresh_token = str(body.get('refreshToken') or '')
    if not refresh_token:
        return JsonResponse({'ok': False, 'error': 'refresh_token_required'}, status=400)

    try:
        decoded = auth_jwt.verify(refresh_token, expected_typ='refresh')
    except Exception as e:
        return JsonResponse({'ok': False, 'error': 'refresh_invalid', 'message': str(e)}, status=401)

    row = find_user_by_sabun(decoded.get('sabun'))
    if not row:
        return JsonResponse({'ok': False, 'error': 'user_not_found'}, status=404)

    session_user = build_session_user(row)
    tokens = auth_jwt.sign(session_user)
    return JsonResponse(login_response(session_user, tokens, list_valid_names()))


@csrf_exempt
def admin_unlock(request, *args, **kwargs):
    # TODO: apiAuth 글로벌 JWT 게이트(req.user) 구현 후 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/auth.js"}, status=501)


@csrf_exempt
def auth_config_get(request, *args, **kwargs):
    # TODO: apiAuth 글로벌 JWT 게이트(req.user) 구현 후 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/auth.js"}, status=501)


@csrf_exempt
def auth_config_save(request, *args, **kwargs):
    # TODO: apiAuth 글로벌 JWT 게이트(req.user) 구현 후 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/auth.js"}, status=501)
