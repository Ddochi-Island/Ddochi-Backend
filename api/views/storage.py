"""storage.js 포팅 대상 — storage 라우트 스텁 (구조만, 로직은 미구현)."""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def storage_upload(request, *args, **kwargs):
    # TODO: services/main/src/routes/storage.js 의 POST /storage/upload 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/storage.js"}, status=501)


@csrf_exempt
def storage_image(request, *args, **kwargs):
    # TODO: services/main/src/routes/storage.js 의 GET /storage/image 포팅
    if request.method not in ['GET']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/storage.js"}, status=501)

