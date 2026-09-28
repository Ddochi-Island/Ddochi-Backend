# shed 어드민(외부 Vercel 사이트)이 브라우저에서 /api/shed/*를 호출할 수 있게 하는 CORS 미들웨어
from django.conf import settings
from django.http import HttpResponse

# 레거시 services/main/src/middleware/cors.js 이식 — 단, 전역이 아니라 shed 경로에만 적용
# (shed origin에 JWT 보호 API까지 열어줄 이유가 없어서). 프리플라이트는 뷰/인증 전에 끊음.
_SHED_PREFIX = '/api/shed/'


class ShedCorsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.headers.get('Origin')
        if not origin or not request.path.startswith(_SHED_PREFIX):
            return self.get_response(request)

        allowed = origin in settings.CORS_ALLOWED_ORIGINS
        if request.method == 'OPTIONS':
            response = HttpResponse(status=204 if allowed else 403)
        else:
            response = self.get_response(request)

        if allowed:
            response['Access-Control-Allow-Origin'] = origin
            response['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
            response['Access-Control-Allow-Headers'] = 'X-Shed-Key, Content-Type'
            response['Access-Control-Max-Age'] = '600'
            response['Vary'] = 'Origin'
        return response
