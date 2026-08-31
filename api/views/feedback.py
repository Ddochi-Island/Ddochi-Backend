"""feedback.js 포팅 대상 — feedback 라우트 스텁 (구조만, 로직은 미구현)."""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def feedback_slots_list(request, *args, **kwargs):
    # TODO: services/main/src/routes/feedback.js 의 POST /feedback-slots/list 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/feedback.js"}, status=501)


@csrf_exempt
def feedback_slots_create(request, *args, **kwargs):
    # TODO: services/main/src/routes/feedback.js 의 POST /feedback-slots/create 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/feedback.js"}, status=501)


@csrf_exempt
def feedback_slots_delete(request, *args, **kwargs):
    # TODO: services/main/src/routes/feedback.js 의 POST /feedback-slots/delete 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/feedback.js"}, status=501)


@csrf_exempt
def feedback_slots_book(request, *args, **kwargs):
    # TODO: services/main/src/routes/feedback.js 의 POST /feedback-slots/book 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/feedback.js"}, status=501)


@csrf_exempt
def feedback_slots_cancel(request, *args, **kwargs):
    # TODO: services/main/src/routes/feedback.js 의 POST /feedback-slots/cancel 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/feedback.js"}, status=501)


@csrf_exempt
def feedback_slots_pass_list(request, *args, **kwargs):
    # TODO: services/main/src/routes/feedback.js 의 POST /feedback-slots/pass-list 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/feedback.js"}, status=501)


@csrf_exempt
def feedback_slots_result(request, *args, **kwargs):
    # TODO: services/main/src/routes/feedback.js 의 POST /feedback-slots/result 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/feedback.js"}, status=501)

