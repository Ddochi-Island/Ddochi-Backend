"""adminAuditLog.js 포팅 대상 — admin_audit_log 라우트 스텁 (구조만, 로직은 미구현)."""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def get_admin_audit_log(request, *args, **kwargs):
    # TODO: services/main/src/routes/adminAuditLog.js 의 POST /get-admin-audit-log 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/adminAuditLog.js"}, status=501)


@csrf_exempt
def cron_logs(request, *args, **kwargs):
    # TODO: services/main/src/routes/adminAuditLog.js 의 GET /cron-logs 포팅
    if request.method not in ['GET']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/adminAuditLog.js"}, status=501)

