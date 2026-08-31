"""internalTelegram.js 포팅 대상 — internal_telegram 라우트 스텁 (구조만, 로직은 미구현)."""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def telegram_callback(request, *args, **kwargs):
    # TODO: services/main/src/routes/internalTelegram.js 의 POST /telegram/callback 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/internalTelegram.js"}, status=501)

