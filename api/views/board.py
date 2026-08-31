"""board.js 포팅 대상 — board 라우트 스텁 (구조만, 로직은 미구현)."""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def board_manage(request, *args, **kwargs):
    # TODO: services/main/src/routes/board.js 의 POST /board/manage 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/board.js"}, status=501)


@csrf_exempt
def post_manage(request, *args, **kwargs):
    # TODO: services/main/src/routes/board.js 의 POST /post/manage 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/board.js"}, status=501)


@csrf_exempt
def post_interact(request, *args, **kwargs):
    # TODO: services/main/src/routes/board.js 의 POST /post/interact 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/board.js"}, status=501)


@csrf_exempt
def comment_manage(request, *args, **kwargs):
    # TODO: services/main/src/routes/board.js 의 POST /comment/manage 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/board.js"}, status=501)

