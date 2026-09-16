# 인라인 버튼 callback_data HMAC 검증 — services/main/src/lib/callbackHmac.js(서명)의 짝
import base64
import hashlib
import hmac
import re
import time

ACTION_RE = re.compile(r'^[a-z0-9_-]+$', re.IGNORECASE)


def _compute_hmac(secret, action, args, ts, chat_id):
    msg = f'{action}|{args}|{ts}|{chat_id}'
    digest = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode()[:11]


def verify_callback_data(secret, callback_data, chat_id, ts_window_ms, now=None):
    if not secret:
        return {'ok': False, 'reason': 'hmac_secret_unset'}
    if not callback_data:
        return {'ok': False, 'reason': 'empty'}

    parts = callback_data.split('|')
    if len(parts) != 4:
        return {'ok': False, 'reason': 'bad_format'}
    action, args, ts_str, mac = parts
    if not ACTION_RE.match(action):
        return {'ok': False, 'reason': 'bad_action'}
    try:
        ts = int(ts_str)
    except ValueError:
        return {'ok': False, 'reason': 'bad_ts'}

    now = now if now is not None else int(time.time() * 1000)
    if abs(now - ts) > ts_window_ms:
        return {'ok': False, 'reason': 'ts_expired'}

    expected = _compute_hmac(secret, action, args, ts, chat_id)
    if not hmac.compare_digest(mac, expected):
        return {'ok': False, 'reason': 'hmac_mismatch'}

    return {'ok': True, 'action': action, 'args': args, 'ts': ts}
