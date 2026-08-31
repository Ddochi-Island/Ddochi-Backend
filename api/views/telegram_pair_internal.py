"""telegramPair.js 포팅 대상 — telegram_pair_internal 라우트 스텁 (구조만, 로직은 미구현)."""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def telegram_pair_complete(request, *args, **kwargs):
    # TODO: services/main/src/routes/telegramPair.js 의 POST /telegram/pair-complete 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/telegramPair.js"}, status=501)

