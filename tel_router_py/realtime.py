# 합당한 자 실시간 신호 — 브라우저 웹소켓(/ws/hapdang)에 "바뀜" 신호만 뿌림. 데이터는 화면이 기존 API로 다시 불러옴.
# tel_router는 uvicorn 한 프로세스라 메모리 안의 접속 목록으로 바로 브로드캐스트(Redis 없이).
import logging

import jwt

import config

logger = logging.getLogger('tel_router.realtime')
_clients = set()


def verify_token(token):
    """Django가 발급한 access JWT(HS256, 같은 JWT_SECRET) → 사번. 아니면 None."""
    if not config.JWT_SECRET or not token:
        return None
    try:
        claims = jwt.decode(token, config.JWT_SECRET, algorithms=['HS256'])
    except jwt.PyJWTError:
        return None
    return claims.get('sabun') if claims.get('typ') == 'access' else None


def add(ws):
    _clients.add(ws)


def remove(ws):
    _clients.discard(ws)


async def broadcast(message):
    for ws in list(_clients):
        try:
            await ws.send_json(message)
        except Exception:
            _clients.discard(ws)
    return len(_clients)


if __name__ == '__main__':  # python realtime.py — 토큰 확인 자체 점검
    import time
    config.JWT_SECRET = 's'
    good = jwt.encode({'sabun': 'A1', 'typ': 'access', 'exp': time.time() + 60}, 's', algorithm='HS256')
    assert verify_token(good) == 'A1'
    assert verify_token(jwt.encode({'sabun': 'A1', 'typ': 'refresh', 'exp': time.time() + 60}, 's', algorithm='HS256')) is None
    assert verify_token(jwt.encode({'sabun': 'A1', 'typ': 'access', 'exp': time.time() - 1}, 's', algorithm='HS256')) is None
    assert verify_token(jwt.encode({'sabun': 'A1', 'typ': 'access'}, 'other', algorithm='HS256')) is None
    assert verify_token('') is None
    print('ok')
