"""cronInternal.js 포팅 대상 — cron_internal 라우트 스텁 (구조만, 로직은 미구현)."""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from api.clients.data_router import DataRouterClient
from api.telegram.internal_auth import check_internal_auth
from api.telegram.prospect_dashboard import send_fresh_prospect_dashboard
from api.telegram.team_config import list_prospect_chat_team_ids


@csrf_exempt
def broadcast_status(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 GET /broadcast-status 포팅
    if request.method not in ['GET']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def send_prayer(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /send-prayer 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def send_stats(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /send-stats 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def update_stats(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /update-stats 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def send_checkin(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /send-checkin 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def send_activity_coord(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /send-activity-coord 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def send_morning_briefing(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /send-morning-briefing 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def send_current_schedule(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /send-current-schedule 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def send_activity_report(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /send-activity-report 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def send_weekly_report(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /send-weekly-report 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def send_prospect_dashboard(request, *args, **kwargs):
    """정각 크론(외부 cron-router가 매시 호출) — 찾기현황판 연결된 팀마다 새 메시지를
    보내고 직전 메시지를 지운다. 이벤트(제출/재가/버튼)로 인한 edit-in-place 갱신과
    별개 — 그건 api/telegram/prospect_dashboard.py의 refresh_prospect_dashboard."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    if not check_internal_auth(request):
        return JsonResponse({'error': 'unauthorized'}, status=401)

    client = DataRouterClient()
    results = {}
    for team_id in list_prospect_chat_team_ids(client):
        try:
            results[team_id] = send_fresh_prospect_dashboard(client, team_id)
        except Exception as e:
            results[team_id] = {'sent': False, 'error': str(e)}
    return JsonResponse({'success': True, 'results': results})


@csrf_exempt
def update_prospect_dashboard(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /update-prospect-dashboard 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def send_feedback_dashboard(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /send-feedback-dashboard 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def send_matching_dashboard(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /send-matching-dashboard 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def update_matching_dashboard(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /update-matching-dashboard 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def send_return_home(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /send-return-home 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def sync_pii_hash(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /sync-pii-hash 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def ttl_pii_hash(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /ttl-pii-hash 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def update_sheet_dashboard(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /update-sheet-dashboard 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def send_sheet_dashboard(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /send-sheet-dashboard 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def update_talk_dashboard(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /update-talk-dashboard 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def send_talk_dashboard(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /send-talk-dashboard 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def sync_intake(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /sync-intake 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def logs(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 GET /logs 포팅
    if request.method not in ['GET']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def send_shed_unified_dashboard(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /send-shed-unified-dashboard 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def update_shed_unified_dashboard(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /update-shed-unified-dashboard 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def send_shed_tm_dashboard(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /send-shed-tm-dashboard 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def update_shed_tm_dashboard(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /update-shed-tm-dashboard 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def send_shed_sched_dashboard(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /send-shed-sched-dashboard 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def update_shed_sched_dashboard(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /update-shed-sched-dashboard 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def send_shed_246_dashboard(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /send-shed-246-dashboard 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def update_shed_246_dashboard(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /update-shed-246-dashboard 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def send_shed_246_tm_dashboard(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /send-shed-246-tm-dashboard 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def update_shed_246_tm_dashboard(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /update-shed-246-tm-dashboard 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def send_shed_246_sched_dashboard(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /send-shed-246-sched-dashboard 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)


@csrf_exempt
def update_shed_246_sched_dashboard(request, *args, **kwargs):
    # TODO: services/main/src/routes/cronInternal.js 의 POST /update-shed-246-sched-dashboard 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/cronInternal.js"}, status=501)

