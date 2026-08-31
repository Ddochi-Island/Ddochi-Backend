"""locks.js 포팅 대상 — locks 라우트 스텁 (구조만, 로직은 미구현)."""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def lock_acquire(request, *args, **kwargs):
    # TODO: services/main/src/routes/locks.js 의 POST /lock/acquire 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/locks.js"}, status=501)


@csrf_exempt
def lock_heartbeat(request, *args, **kwargs):
    # TODO: services/main/src/routes/locks.js 의 POST /lock/heartbeat 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/locks.js"}, status=501)


@csrf_exempt
def lock_release(request, *args, **kwargs):
    # TODO: services/main/src/routes/locks.js 의 POST /lock/release 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/locks.js"}, status=501)

