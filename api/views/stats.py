"""stats.js 포팅 대상 — stats 라우트 스텁 (구조만, 로직은 미구현)."""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def get_week_start_dow(request, *args, **kwargs):
    # TODO: services/main/src/routes/stats.js 의 POST /get-week-start-dow 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/stats.js"}, status=501)


@csrf_exempt
def set_week_start_global(request, *args, **kwargs):
    # TODO: services/main/src/routes/stats.js 의 POST /set-week-start-global 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/stats.js"}, status=501)


@csrf_exempt
def set_week_start_personal(request, *args, **kwargs):
    # TODO: services/main/src/routes/stats.js 의 POST /set-week-start-personal 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/stats.js"}, status=501)


@csrf_exempt
def my_archive(request, *args, **kwargs):
    # TODO: services/main/src/routes/stats.js 의 POST /my-archive 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/stats.js"}, status=501)


@csrf_exempt
def my_goal(request, *args, **kwargs):
    # TODO: services/main/src/routes/stats.js 의 POST /my-goal 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/stats.js"}, status=501)


@csrf_exempt
def get_stats_password(request, *args, **kwargs):
    # TODO: services/main/src/routes/stats.js 의 POST /get-stats-password 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/stats.js"}, status=501)


@csrf_exempt
def get_personal_stats(request, *args, **kwargs):
    # TODO: services/main/src/routes/stats.js 의 POST /get-personal-stats 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/stats.js"}, status=501)


@csrf_exempt
def get_comprehensive_stats(request, *args, **kwargs):
    # TODO: services/main/src/routes/stats.js 의 POST /get-comprehensive-stats 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/stats.js"}, status=501)


@csrf_exempt
def get_weekly_record(request, *args, **kwargs):
    # TODO: services/main/src/routes/stats.js 의 POST /get-weekly-record 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/stats.js"}, status=501)


@csrf_exempt
def get_telegram_goals(request, *args, **kwargs):
    # TODO: services/main/src/routes/stats.js 의 POST /get-telegram-goals 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/stats.js"}, status=501)


@csrf_exempt
def save_telegram_goals(request, *args, **kwargs):
    # TODO: services/main/src/routes/stats.js 의 POST /save-telegram-goals 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/stats.js"}, status=501)


@csrf_exempt
def send_morning_briefing(request, *args, **kwargs):
    # TODO: services/main/src/routes/stats.js 의 POST /send-morning-briefing 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/stats.js"}, status=501)


@csrf_exempt
def send_weekly_report(request, *args, **kwargs):
    # TODO: services/main/src/routes/stats.js 의 POST /send-weekly-report 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/stats.js"}, status=501)


@csrf_exempt
def send_comparison_report(request, *args, **kwargs):
    # TODO: services/main/src/routes/stats.js 의 POST /send-comparison-report 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/stats.js"}, status=501)

