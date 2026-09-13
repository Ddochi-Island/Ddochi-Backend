# 합재양 인라인 버튼 callback_data 서명 — tel_router_py의 hmac_verify.py와 짝(포맷/시크릿 동일해야 함)
import base64
import hashlib
import hmac
import time

HMAC_BYTES = 8
SEPARATOR = '|'


def _compute_hmac(secret, action, args, ts, chat_id):
    msg = f'{action}{SEPARATOR}{args}{SEPARATOR}{ts}{SEPARATOR}{chat_id}'
    digest = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode()[:11]


def sign_callback_data(secret, action, args, chat_id):
    ts = int(time.time() * 1000)
    mac = _compute_hmac(secret, action, args, ts, chat_id)
    return f'{action}{SEPARATOR}{args}{SEPARATOR}{ts}{SEPARATOR}{mac}'
