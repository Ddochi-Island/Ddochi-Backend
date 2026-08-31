"""auth.js 포팅 대상 — auth 라우트 스텁 (구조만, 로직은 미구현)."""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def login(request, *args, **kwargs):
    # TODO: services/main/src/routes/auth.js 의 POST /login 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/auth.js"}, status=501)


@csrf_exempt
def refresh(request, *args, **kwargs):
    # TODO: services/main/src/routes/auth.js 의 POST /refresh 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/auth.js"}, status=501)


@csrf_exempt
def admin_unlock(request, *args, **kwargs):
    # TODO: services/main/src/routes/auth.js 의 POST /admin-unlock 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/auth.js"}, status=501)


@csrf_exempt
def auth_config_get(request, *args, **kwargs):
    # TODO: services/main/src/routes/auth.js 의 POST /auth-config/get 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/auth.js"}, status=501)


@csrf_exempt
def auth_config_save(request, *args, **kwargs):
    # TODO: services/main/src/routes/auth.js 의 POST /auth-config/save 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/auth.js"}, status=501)

