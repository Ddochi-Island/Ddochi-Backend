# tel_router → main "/internal/telegram/*" 콜백 공통 Bearer 인증 — pair-complete/callback가 같이 씀
import hmac

from django.conf import settings


def check_internal_auth(request):
    token = settings.TELEGRAM_INTERNAL_TOKEN
    if not token:
        return False
    got = request.headers.get('Authorization', '')
    if got.startswith('Bearer '):
        got = got[len('Bearer '):]
    if len(got) != len(token):
        return False
    return hmac.compare_digest(got, token)
