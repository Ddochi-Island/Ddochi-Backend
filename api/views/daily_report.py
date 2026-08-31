"""dailyReport.js 포팅 대상 — daily_report 라우트 스텁 (구조만, 로직은 미구현)."""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def daily_report_list_names(request, *args, **kwargs):
    # TODO: services/main/src/routes/dailyReport.js 의 POST /daily-report/list-names 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dailyReport.js"}, status=501)


@csrf_exempt
def daily_report_get(request, *args, **kwargs):
    # TODO: services/main/src/routes/dailyReport.js 의 POST /daily-report/get 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dailyReport.js"}, status=501)


@csrf_exempt
def daily_report(request, *args, **kwargs):
    # TODO: services/main/src/routes/dailyReport.js 의 POST /daily-report 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dailyReport.js"}, status=501)


@csrf_exempt
def daily_report_search_reg(request, *args, **kwargs):
    # TODO: services/main/src/routes/dailyReport.js 의 POST /daily-report/search-reg 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dailyReport.js"}, status=501)


@csrf_exempt
def daily_report_add_reg_entry(request, *args, **kwargs):
    # TODO: services/main/src/routes/dailyReport.js 의 POST /daily-report/add-reg-entry 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dailyReport.js"}, status=501)


@csrf_exempt
def get_my_plan(request, *args, **kwargs):
    # TODO: services/main/src/routes/dailyReport.js 의 POST /get-my-plan 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dailyReport.js"}, status=501)


@csrf_exempt
def update_today_plan(request, *args, **kwargs):
    # TODO: services/main/src/routes/dailyReport.js 의 POST /update-today-plan 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dailyReport.js"}, status=501)


@csrf_exempt
def get_missed_executions(request, *args, **kwargs):
    # TODO: services/main/src/routes/dailyReport.js 의 POST /get-missed-executions 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dailyReport.js"}, status=501)


@csrf_exempt
def get_plan_execution(request, *args, **kwargs):
    # TODO: services/main/src/routes/dailyReport.js 의 POST /get-plan-execution 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dailyReport.js"}, status=501)


@csrf_exempt
def update_plan_execution(request, *args, **kwargs):
    # TODO: services/main/src/routes/dailyReport.js 의 POST /update-plan-execution 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dailyReport.js"}, status=501)


@csrf_exempt
def batch_update_executions(request, *args, **kwargs):
    # TODO: services/main/src/routes/dailyReport.js 의 POST /batch-update-executions 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dailyReport.js"}, status=501)


@csrf_exempt
def weekly_template_get(request, *args, **kwargs):
    # TODO: services/main/src/routes/dailyReport.js 의 POST /weekly-template/get 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dailyReport.js"}, status=501)


@csrf_exempt
def weekly_template_save_all(request, *args, **kwargs):
    # TODO: services/main/src/routes/dailyReport.js 의 POST /weekly-template/save-all 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dailyReport.js"}, status=501)


@csrf_exempt
def get_audit_logs(request, *args, **kwargs):
    # TODO: services/main/src/routes/dailyReport.js 의 POST /get-audit-logs 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dailyReport.js"}, status=501)


@csrf_exempt
def daily_report_reflections(request, *args, **kwargs):
    # TODO: services/main/src/routes/dailyReport.js 의 POST /daily-report/reflections 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dailyReport.js"}, status=501)

