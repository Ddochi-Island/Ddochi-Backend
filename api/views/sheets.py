"""sheets.js 포팅 대상 — sheets 라우트 스텁 (구조만, 로직은 미구현)."""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def get_sheet_configs(request, *args, **kwargs):
    # TODO: services/main/src/routes/sheets.js 의 POST /get-sheet-configs 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/sheets.js"}, status=501)


@csrf_exempt
def get_sheet_prospects(request, *args, **kwargs):
    # TODO: services/main/src/routes/sheets.js 의 POST /get-sheet-prospects 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/sheets.js"}, status=501)


@csrf_exempt
def fetch_sheet_data(request, *args, **kwargs):
    # TODO: services/main/src/routes/sheets.js 의 POST /fetch-sheet-data 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/sheets.js"}, status=501)


@csrf_exempt
def test_sheet_access(request, *args, **kwargs):
    # TODO: services/main/src/routes/sheets.js 의 POST /test-sheet-access 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/sheets.js"}, status=501)


@csrf_exempt
def save_sheet_config(request, *args, **kwargs):
    # TODO: services/main/src/routes/sheets.js 의 POST /save-sheet-config 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/sheets.js"}, status=501)


@csrf_exempt
def delete_sheet_config(request, *args, **kwargs):
    # TODO: services/main/src/routes/sheets.js 의 POST /delete-sheet-config 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/sheets.js"}, status=501)


@csrf_exempt
def sheet_sync_trigger(request, *args, **kwargs):
    # TODO: services/main/src/routes/sheets.js 의 POST /sheet-sync/trigger 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/sheets.js"}, status=501)


@csrf_exempt
def send_sheet_dashboard(request, *args, **kwargs):
    # TODO: services/main/src/routes/sheets.js 의 POST /send-sheet-dashboard 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/sheets.js"}, status=501)


@csrf_exempt
def sheet_sync_progress(request, *args, **kwargs):
    # TODO: services/main/src/routes/sheets.js 의 POST /sheet-sync/progress 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/sheets.js"}, status=501)


@csrf_exempt
def manage_sheet_config_order(request, *args, **kwargs):
    # TODO: services/main/src/routes/sheets.js 의 POST /manage-sheet-config-order 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/sheets.js"}, status=501)


@csrf_exempt
def update_import_status(request, *args, **kwargs):
    # TODO: services/main/src/routes/sheets.js 의 POST /update-import-status 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/sheets.js"}, status=501)


@csrf_exempt
def delete_import_status(request, *args, **kwargs):
    # TODO: services/main/src/routes/sheets.js 의 POST /delete-import-status 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/sheets.js"}, status=501)


@csrf_exempt
def tm_sheet_my_configs(request, *args, **kwargs):
    # TODO: services/main/src/routes/sheets.js 의 POST /tm-sheet/my-configs 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/sheets.js"}, status=501)


@csrf_exempt
def tm_sheet_events(request, *args, **kwargs):
    # TODO: services/main/src/routes/sheets.js 의 GET /tm-sheet/events 포팅
    if request.method not in ['GET']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/sheets.js"}, status=501)


@csrf_exempt
def tm_sheet_rows(request, *args, **kwargs):
    # TODO: services/main/src/routes/sheets.js 의 POST /tm-sheet/rows 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/sheets.js"}, status=501)


@csrf_exempt
def tm_sheet_add_row(request, *args, **kwargs):
    # TODO: services/main/src/routes/sheets.js 의 POST /tm-sheet/add-row 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/sheets.js"}, status=501)


@csrf_exempt
def tm_sheet_save_row(request, *args, **kwargs):
    # TODO: services/main/src/routes/sheets.js 의 POST /tm-sheet/save-row 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/sheets.js"}, status=501)


@csrf_exempt
def tm_sheet_delete_row(request, *args, **kwargs):
    # TODO: services/main/src/routes/sheets.js 의 POST /tm-sheet/delete-row 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/sheets.js"}, status=501)


@csrf_exempt
def sheet_view_rows(request, *args, **kwargs):
    # TODO: services/main/src/routes/sheets.js 의 POST /sheet-view/rows 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/sheets.js"}, status=501)


@csrf_exempt
def sheet_view_update_cell(request, *args, **kwargs):
    # TODO: services/main/src/routes/sheets.js 의 POST /sheet-view/update-cell 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/sheets.js"}, status=501)


@csrf_exempt
def sheet_view_append_row(request, *args, **kwargs):
    # TODO: services/main/src/routes/sheets.js 의 POST /sheet-view/append-row 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/sheets.js"}, status=501)


@csrf_exempt
def sheet_view_col_validations(request, *args, **kwargs):
    # TODO: services/main/src/routes/sheets.js 의 POST /sheet-view/col-validations 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/sheets.js"}, status=501)


@csrf_exempt
def sheet_view_delete_row(request, *args, **kwargs):
    # TODO: services/main/src/routes/sheets.js 의 POST /sheet-view/delete-row 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/sheets.js"}, status=501)

