"""areaScore.js 포팅 대상 — area_score 라우트 스텁 (구조만, 로직은 미구현)."""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def area_score_today(request, *args, **kwargs):
    # TODO: services/main/src/routes/areaScore.js 의 POST /area-score/today 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/areaScore.js"}, status=501)


@csrf_exempt
def area_score_toggle(request, *args, **kwargs):
    # TODO: services/main/src/routes/areaScore.js 의 POST /area-score/toggle 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/areaScore.js"}, status=501)


@csrf_exempt
def area_score_unlock_requests(request, *args, **kwargs):
    # TODO: services/main/src/routes/areaScore.js 의 POST /area-score/unlock-requests 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/areaScore.js"}, status=501)


@csrf_exempt
def area_score_unlock_requests_list(request, *args, **kwargs):
    # TODO: services/main/src/routes/areaScore.js 의 POST /area-score/unlock-requests/list 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/areaScore.js"}, status=501)


@csrf_exempt
def area_score_unlock_requests_id_complete(request, *args, **kwargs):
    # TODO: services/main/src/routes/areaScore.js 의 POST /area-score/unlock-requests/:id/complete 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/areaScore.js"}, status=501)


@csrf_exempt
def area_score_mission_complete(request, *args, **kwargs):
    # TODO: services/main/src/routes/areaScore.js 의 POST /area-score/mission/complete 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/areaScore.js"}, status=501)


@csrf_exempt
def area_score_area_detail(request, *args, **kwargs):
    # TODO: services/main/src/routes/areaScore.js 의 POST /area-score/area-detail 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/areaScore.js"}, status=501)


@csrf_exempt
def area_score_area_add(request, *args, **kwargs):
    # TODO: services/main/src/routes/areaScore.js 의 POST /area-score/area/add 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/areaScore.js"}, status=501)


@csrf_exempt
def area_score_area_remove_last(request, *args, **kwargs):
    # TODO: services/main/src/routes/areaScore.js 의 POST /area-score/area/remove-last 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/areaScore.js"}, status=501)

