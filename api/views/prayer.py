"""prayer.js 포팅 대상 — prayer 라우트 스텁 (구조만, 로직은 미구현)."""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def submit_prayer(request, *args, **kwargs):
    # TODO: services/main/src/routes/prayer.js 의 POST /submit-prayer 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/prayer.js"}, status=501)

