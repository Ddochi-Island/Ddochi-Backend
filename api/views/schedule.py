"""schedule.js 포팅 대상 — schedule 라우트 스텁 (구조만, 로직은 미구현)."""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def get_semester_schedule(request, *args, **kwargs):
    # TODO: services/main/src/routes/schedule.js 의 POST /get-semester-schedule 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/schedule.js"}, status=501)


@csrf_exempt
def save_semester_schedule(request, *args, **kwargs):
    # TODO: services/main/src/routes/schedule.js 의 POST /save-semester-schedule 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/schedule.js"}, status=501)


@csrf_exempt
def activity_schedule_get(request, *args, **kwargs):
    # TODO: services/main/src/routes/schedule.js 의 POST /activity-schedule/get 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/schedule.js"}, status=501)


@csrf_exempt
def activity_schedule_save(request, *args, **kwargs):
    # TODO: services/main/src/routes/schedule.js 의 POST /activity-schedule/save 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/schedule.js"}, status=501)


@csrf_exempt
def save_activity_report_schedule(request, *args, **kwargs):
    # TODO: services/main/src/routes/schedule.js 의 POST /save-activity-report-schedule 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/schedule.js"}, status=501)


@csrf_exempt
def save_current_schedule_config(request, *args, **kwargs):
    # TODO: services/main/src/routes/schedule.js 의 POST /save-current-schedule-config 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/schedule.js"}, status=501)


@csrf_exempt
def save_activity_coord_config(request, *args, **kwargs):
    # TODO: services/main/src/routes/schedule.js 의 POST /save-activity-coord-config 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/schedule.js"}, status=501)


@csrf_exempt
def trigger_activity_coord(request, *args, **kwargs):
    # TODO: services/main/src/routes/schedule.js 의 POST /trigger-activity-coord 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/schedule.js"}, status=501)


@csrf_exempt
def trigger_current_schedule(request, *args, **kwargs):
    # TODO: services/main/src/routes/schedule.js 의 POST /trigger-current-schedule 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/schedule.js"}, status=501)


@csrf_exempt
def trigger_activity_report(request, *args, **kwargs):
    # TODO: services/main/src/routes/schedule.js 의 POST /trigger-activity-report 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/schedule.js"}, status=501)


@csrf_exempt
def test_activity_report(request, *args, **kwargs):
    # TODO: services/main/src/routes/schedule.js 의 POST /test-activity-report 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/schedule.js"}, status=501)

