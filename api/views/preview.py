"""preview.js 포팅 대상 — preview 라우트 스텁 (구조만, 로직은 미구현)."""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def preview_activity_coord(request, *args, **kwargs):
    # TODO: services/main/src/routes/preview.js 의 POST /preview-activity-coord 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/preview.js"}, status=501)


@csrf_exempt
def preview_current_schedule(request, *args, **kwargs):
    # TODO: services/main/src/routes/preview.js 의 POST /preview-current-schedule 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/preview.js"}, status=501)


@csrf_exempt
def preview_activity_report(request, *args, **kwargs):
    # TODO: services/main/src/routes/preview.js 의 POST /preview-activity-report 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/preview.js"}, status=501)

