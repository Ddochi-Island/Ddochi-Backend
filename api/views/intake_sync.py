"""intakeSync.js 포팅 대상 — intake_sync 라우트 스텁 (구조만, 로직은 미구현)."""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def intake_sheet_meta(request, *args, **kwargs):
    # TODO: services/main/src/routes/intakeSync.js 의 POST /intake/sheet-meta 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/intakeSync.js"}, status=501)


@csrf_exempt
def intake_sheet_tab_rows(request, *args, **kwargs):
    # TODO: services/main/src/routes/intakeSync.js 의 POST /intake/sheet-tab-rows 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/intakeSync.js"}, status=501)


@csrf_exempt
def intake_save_config(request, *args, **kwargs):
    # TODO: services/main/src/routes/intakeSync.js 의 POST /intake/save-config 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/intakeSync.js"}, status=501)


@csrf_exempt
def intake_list_configs(request, *args, **kwargs):
    # TODO: services/main/src/routes/intakeSync.js 의 POST /intake/list-configs 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/intakeSync.js"}, status=501)


@csrf_exempt
def intake_delete_config(request, *args, **kwargs):
    # TODO: services/main/src/routes/intakeSync.js 의 POST /intake/delete-config 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/intakeSync.js"}, status=501)


@csrf_exempt
def intake_sync_now(request, *args, **kwargs):
    # TODO: services/main/src/routes/intakeSync.js 의 POST /intake/sync-now 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/intakeSync.js"}, status=501)


@csrf_exempt
def intake_list_prospects(request, *args, **kwargs):
    # TODO: services/main/src/routes/intakeSync.js 의 POST /intake/list-prospects 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/intakeSync.js"}, status=501)


@csrf_exempt
def intake_save_row(request, *args, **kwargs):
    # TODO: services/main/src/routes/intakeSync.js 의 POST /intake/save-row 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/intakeSync.js"}, status=501)


@csrf_exempt
def intake_delete_row(request, *args, **kwargs):
    # TODO: services/main/src/routes/intakeSync.js 의 POST /intake/delete-row 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/intakeSync.js"}, status=501)


@csrf_exempt
def intake_events(request, *args, **kwargs):
    # TODO: services/main/src/routes/intakeSync.js 의 GET /intake/events 포팅
    if request.method not in ['GET']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/intakeSync.js"}, status=501)


@csrf_exempt
def intake_assign_manager(request, *args, **kwargs):
    # TODO: services/main/src/routes/intakeSync.js 의 POST /intake/assign-manager 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/intakeSync.js"}, status=501)


@csrf_exempt
def intake_dup_resolve(request, *args, **kwargs):
    # TODO: services/main/src/routes/intakeSync.js 의 POST /intake/dup-resolve 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/intakeSync.js"}, status=501)

