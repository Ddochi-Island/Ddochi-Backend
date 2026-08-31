"""adminUsers.js 포팅 대상 — admin_users 라우트 스텁 (구조만, 로직은 미구현)."""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def admin_users_list(request, *args, **kwargs):
    # TODO: services/main/src/routes/adminUsers.js 의 POST /admin/users/list 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/adminUsers.js"}, status=501)


@csrf_exempt
def admin_users_meta(request, *args, **kwargs):
    # TODO: services/main/src/routes/adminUsers.js 의 POST /admin/users/meta 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/adminUsers.js"}, status=501)


@csrf_exempt
def admin_users_create(request, *args, **kwargs):
    # TODO: services/main/src/routes/adminUsers.js 의 POST /admin/users/create 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/adminUsers.js"}, status=501)


@csrf_exempt
def admin_users_update(request, *args, **kwargs):
    # TODO: services/main/src/routes/adminUsers.js 의 POST /admin/users/update 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/adminUsers.js"}, status=501)


@csrf_exempt
def admin_users_bulk_update(request, *args, **kwargs):
    # TODO: services/main/src/routes/adminUsers.js 의 POST /admin/users/bulk-update 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/adminUsers.js"}, status=501)


@csrf_exempt
def admin_users_swap_teams(request, *args, **kwargs):
    # TODO: services/main/src/routes/adminUsers.js 의 POST /admin/users/swap-teams 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/adminUsers.js"}, status=501)

