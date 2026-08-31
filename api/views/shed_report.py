"""shedReport.js 포팅 대상 — shed_report 라우트 스텁 (구조만, 로직은 미구현)."""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def shed_report(request, *args, **kwargs):
    # TODO: services/main/src/routes/shedReport.js 의 GET /shed/report 포팅
    if request.method not in ['GET']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/shedReport.js"}, status=501)

