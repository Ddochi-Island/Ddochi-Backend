"""sheetSync.js 포팅 대상 — sheet_sync 라우트 스텁 (구조만, 로직은 미구현)."""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def sheet_sync(request, *args, **kwargs):
    # TODO: services/main/src/routes/sheetSync.js 의 POST /sheet-sync 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/sheetSync.js"}, status=501)

