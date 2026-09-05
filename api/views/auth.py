"""auth.js 포팅 — login/refresh 실제 로직. admin-unlock/auth-config는 apiAuth
글로벌 JWT 게이트가 아직 없어서 스텁으로 남겨둠."""
import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from api.auth import jwt as auth_jwt
from api.auth import passkey
from api.clients.data_router import DataRouterClient, DataRouterError


# members 재설계 — USERS/ROLES를 MEMBERS/POSITION_CODES/MEMBER_POSITION_MAPPINGS/
# MEMBER_AFFILIATION_HISTORIES로 대체. team/area는 MEMBER_AFFILIATION_HISTORIES의
# IS_CURRENT=1 행에서 조회(현재 소속). ROLE_IDS(JSON 배열 컬럼) 대신
# MEMBER_POSITION_MAPPINGS N:M 조인으로 직책을 조회.
def find_user_by_sabun(sabun):
    if not sabun:
        return None
    return DataRouterClient().query_one(
        """SELECT m.MEMBER_ID AS SABUN, m.NAME,
                  mah.REGION_CODE AS TEAM_ID, mah.REGION_CODE AS TEAM_NAME,
                  mah.DISTRICT_CODE AS AREA_ID, mah.DISTRICT_CODE AS AREA_NAME,
                  m.TELEGRAM_ID,
                  (SELECT pc.POSITION_NAME
                     FROM MEMBER_POSITION_MAPPINGS mpm
                     JOIN POSITION_CODES pc ON pc.POSITION_CODE = mpm.POSITION_CODE
                    WHERE mpm.MEMBER_ID = m.MEMBER_ID AND pc.DELETED_AT IS NULL
                    ORDER BY CASE pc.SCOPE WHEN 'global' THEN 0 WHEN 'region' THEN 1 ELSE 2 END
                    FETCH FIRST 1 ROWS ONLY) AS POSITION,
                  (SELECT JSON_ARRAYAGG(jt.PERM RETURNING CLOB)
                     FROM MEMBER_POSITION_MAPPINGS mpm
                     JOIN POSITION_CODES pc ON pc.POSITION_CODE = mpm.POSITION_CODE,
                          JSON_TABLE(pc.PERMISSIONS, '$[*]' COLUMNS (PERM VARCHAR2(50 CHAR) PATH '$')) jt
                    WHERE mpm.MEMBER_ID = m.MEMBER_ID AND pc.DELETED_AT IS NULL) AS PERMS,
                  m.CREATED_AT AS JOINED_AT,
                  m.DELETED_AT
             FROM MEMBERS m
             LEFT JOIN MEMBER_AFFILIATION_HISTORIES mah
               ON mah.MEMBER_ID = m.MEMBER_ID AND mah.IS_CURRENT = 1
            WHERE m.MEMBER_ID = :1 AND m.DELETED_AT IS NULL""",
        [sabun],
        cache_ttl_ms=1_000,
        priority='high',
    )


def list_valid_names():
    try:
        rows = DataRouterClient().query('SELECT NAME FROM MEMBERS WHERE DELETED_AT IS NULL ORDER BY NAME')
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
