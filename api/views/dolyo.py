"""dolyo.js 포팅 대상 — dolyo 라우트 스텁 (구조만, 로직은 미구현)."""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def get_dolyo_list(request, *args, **kwargs):
    # TODO: services/main/src/routes/dolyo.js 의 POST /get-dolyo-list 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dolyo.js"}, status=501)


@csrf_exempt
def register_dolyo(request, *args, **kwargs):
    # TODO: services/main/src/routes/dolyo.js 의 POST /register-dolyo 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dolyo.js"}, status=501)


@csrf_exempt
def update_dolyo(request, *args, **kwargs):
    # TODO: services/main/src/routes/dolyo.js 의 POST /update-dolyo 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dolyo.js"}, status=501)


@csrf_exempt
def add_dolyo_action(request, *args, **kwargs):
    # TODO: services/main/src/routes/dolyo.js 의 POST /add-dolyo-action 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dolyo.js"}, status=501)


@csrf_exempt
def delete_dolyo_action(request, *args, **kwargs):
    # TODO: services/main/src/routes/dolyo.js 의 POST /delete-dolyo-action 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dolyo.js"}, status=501)


@csrf_exempt
def delete_dolyo(request, *args, **kwargs):
    # TODO: services/main/src/routes/dolyo.js 의 POST /delete-dolyo 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dolyo.js"}, status=501)


@csrf_exempt
def dolyo_match_result(request, *args, **kwargs):
    # TODO: services/main/src/routes/dolyo.js 의 POST /dolyo-match-result 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dolyo.js"}, status=501)


@csrf_exempt
def dolyo_approval(request, *args, **kwargs):
    # TODO: services/main/src/routes/dolyo.js 의 POST /dolyo-approval 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dolyo.js"}, status=501)


@csrf_exempt
def submit_dolyo_habjaeyang(request, *args, **kwargs):
    # TODO: services/main/src/routes/dolyo.js 의 POST /submit-dolyo-habjaeyang 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dolyo.js"}, status=501)


@csrf_exempt
def reset_dolyo_result(request, *args, **kwargs):
    # TODO: services/main/src/routes/dolyo.js 의 POST /reset-dolyo-result 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dolyo.js"}, status=501)

