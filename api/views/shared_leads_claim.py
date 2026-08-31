"""sharedLeads.js 포팅 대상 — shared_leads_claim 라우트 스텁 (구조만, 로직은 미구현)."""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def telegram_delete_shared_lead(request, *args, **kwargs):
    # TODO: services/main/src/routes/sharedLeads.js 의 POST /telegram/delete-shared-lead 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/sharedLeads.js"}, status=501)


@csrf_exempt
def telegram_restore_shared_lead(request, *args, **kwargs):
    # TODO: services/main/src/routes/sharedLeads.js 의 POST /telegram/restore-shared-lead 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/sharedLeads.js"}, status=501)


@csrf_exempt
def telegram_claim_shared_lead(request, *args, **kwargs):
    # TODO: services/main/src/routes/sharedLeads.js 의 POST /telegram/claim-shared-lead 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/sharedLeads.js"}, status=501)

