"""ministry.js 포팅 대상 — ministry 라우트 스텁 (구조만, 로직은 미구현)."""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def manage_ministry_categories(request, *args, **kwargs):
    # TODO: services/main/src/routes/ministry.js 의 POST /manage-ministry-categories 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/ministry.js"}, status=501)


@csrf_exempt
def manage_notification_times(request, *args, **kwargs):
    # TODO: services/main/src/routes/ministry.js 의 POST /manage-notification-times 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/ministry.js"}, status=501)

