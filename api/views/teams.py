"""teams.js 포팅 대상 — teams 라우트 스텁 (구조만, 로직은 미구현)."""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def get_teams(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /get-teams 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def get_team_areas(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /get-team-areas 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def connect_telegram(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /connect-telegram 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def get_tool_configs(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /get-tool-configs 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def save_tool_config(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /save-tool-config 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def delete_tool_config(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /delete-tool-config 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def get_path_configs(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /get-path-configs 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def save_path_config(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /save-path-config 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def delete_path_config(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /delete-path-config 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def get_return_home_config(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /get-return-home-config 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def save_return_home_config(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /save-return-home-config 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def get_auto_reject_config(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /get-auto-reject-config 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def save_auto_reject_config(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /save-auto-reject-config 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def team_setting_get(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /team-setting/get 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def team_setting_set(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /team-setting/set 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def save_activity_report_mode(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /save-activity-report-mode 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def link_telegram_user(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /link-telegram-user 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def get_team_cron_config(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /get-team-cron-config 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def set_team_cron_job(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /set-team-cron-job 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def get_scheduled_jobs(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /get-scheduled-jobs 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def toggle_scheduled_job(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /toggle-scheduled-job 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)

