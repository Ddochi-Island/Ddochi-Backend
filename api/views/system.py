"""system.js 포팅 대상 — system 라우트 스텁 (구조만, 로직은 미구현)."""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from api.clients.data_router import DataRouterClient, DataRouterError


@csrf_exempt
def ping(request, *args, **kwargs):
    # TODO: services/main/src/routes/system.js 의 GET /ping 포팅
    # TODO: services/main/src/routes/system.js 의 POST /ping 포팅
    if request.method not in ['GET', 'POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/system.js"}, status=501)


@csrf_exempt
def healthz(request, *args, **kwargs):
    # data_router 연동 확인용 — SELECT SYSDATE로 DB 접근까지 왕복.
    if request.method not in ['GET']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    try:
        row = DataRouterClient().query_one('SELECT SYSDATE FROM DUAL')
    except DataRouterError as e:
        return JsonResponse({"ok": False, "error": e.code, "message": str(e)}, status=502)
    return JsonResponse({"ok": True, "db_time": row["sysdate"]})

