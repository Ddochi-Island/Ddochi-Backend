"""shedUsers.js 포팅 — shed 어드민 유입자 자동완성용 사용자 목록."""
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from api.clients.data_router import DataRouterClient, DataRouterError


@csrf_exempt
def shed_users(request, *args, **kwargs):
    if request.method not in ['GET']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    shed_key = settings.SHED_INTERNAL_KEY
    if not shed_key or request.headers.get('X-Shed-Key') != shed_key:
        return JsonResponse({"ok": False}, status=401)

    try:
        rows = DataRouterClient().query(
            """SELECT NAME, SABUN FROM USERS
                WHERE DELETED_AT IS NULL AND STATUS = 'active' AND SABUN != 'SYSTEM'
                ORDER BY NAME"""
        )
    except DataRouterError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)

    return JsonResponse({"ok": True, "users": [{"name": r["name"], "sabun": r["sabun"]} for r in rows]})
