"""telegramPair.js 포팅 대상 — telegram_pair 라우트 스텁 (구조만, 로직은 미구현)."""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def telegram_pair_start(request, *args, **kwargs):
    # TODO: services/main/src/routes/telegramPair.js 의 POST /telegram-pair/start 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/telegramPair.js"}, status=501)


@csrf_exempt
def telegram_pair_status(request, *args, **kwargs):
    # TODO: services/main/src/routes/telegramPair.js 의 POST /telegram-pair/status 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/telegramPair.js"}, status=501)


@csrf_exempt
def telegram_pair_disconnect(request, *args, **kwargs):
    # TODO: services/main/src/routes/telegramPair.js 의 POST /telegram-pair/disconnect 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/telegramPair.js"}, status=501)


@csrf_exempt
def telegram_link_me(request, *args, **kwargs):
    # TODO: services/main/src/routes/telegramPair.js 의 POST /telegram/link-me 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/telegramPair.js"}, status=501)


@csrf_exempt
def telegram_pair_cancel(request, *args, **kwargs):
    # TODO: services/main/src/routes/telegramPair.js 의 POST /telegram-pair/cancel 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/telegramPair.js"}, status=501)

