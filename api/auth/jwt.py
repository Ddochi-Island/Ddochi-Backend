# services/main/src/auth/jwt.js 포팅 — HS256 access/refresh 토큰 발급·검증.
# TTL은 앱 부팅 시 settings.JWT_ACCESS_TTL/JWT_REFRESH_TTL 로 고정 (jsonwebtoken
# 의 expiresIn 문자열 포맷을 그대로 흉내: "15m", "30d" 등).
import re
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
from django.conf import settings

_TTL_UNITS = {'ms': 0.001, 's': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800, 'y': 31536000}
_TTL_RE = re.compile(r'^(\d+)\s*(ms|s|m|h|d|w|y)?$', re.IGNORECASE)


def _ttl_seconds(ttl):
    m = _TTL_RE.match(str(ttl).strip())
    if not m:
        raise ValueError(f'invalid TTL: {ttl!r}')
    value, unit = m.groups()
    return int(value) * _TTL_UNITS[(unit or 's').lower()]


class WrongTokenTypeError(Exception):
    pass


def sign(user, extra_claims=None):
    now = datetime.now(timezone.utc)
    access_payload = {
        'sabun': user['sabun'],
        'name': user.get('name'),
        'team': user.get('team'),
        'position': user.get('position'),
        'typ': 'access',
        'iat': now,
        'exp': now + timedelta(seconds=_ttl_seconds(settings.JWT_ACCESS_TTL)),
        **(extra_claims or {}),
    }
    refresh_payload = {
        'sabun': user['sabun'],
        'typ': 'refresh',
        'iat': now,
        'exp': now + timedelta(seconds=_ttl_seconds(settings.JWT_REFRESH_TTL)),
    }
    access = pyjwt.encode(access_payload, settings.JWT_SECRET, algorithm='HS256')
    refresh = pyjwt.encode(refresh_payload, settings.JWT_SECRET, algorithm='HS256')
    return {'accessToken': access, 'refreshToken': refresh}


def verify(token, expected_typ='access'):
    decoded = pyjwt.decode(token, settings.JWT_SECRET, algorithms=['HS256'])
    if decoded.get('typ') != expected_typ:
        raise WrongTokenTypeError(f'expected {expected_typ} token')
    return decoded
