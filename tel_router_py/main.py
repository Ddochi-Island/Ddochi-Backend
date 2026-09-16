# tel_router 파이썬 최소 버전 — 텔레그램 웹훅 수신(/pair, 인라인 버튼 callback_query 처리) + main→발송 큐(/enqueue)
# ponytail: 대시보드 SPA/멀티봇/공유 리드 명령은 뺐음. 필요해지면 추가.
import asyncio
import logging

import httpx
from fastapi import FastAPI, Header, HTTPException, Request

import callback
import config
import pairing
import telegram_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('tel_router')

app = FastAPI()
_http_client = None

# 텔레그램이 같은 update를 재전송해도 두 번 처리하지 않기 위한 최소 dedup.
_seen_update_ids = {}
_DEDUP_TTL_S = 300


def _dedup_hit(update_id):
    if update_id is None:
        return False
    now = asyncio.get_event_loop().time()
    for k, t in list(_seen_update_ids.items()):
        if now - t > _DEDUP_TTL_S:
            _seen_update_ids.pop(k, None)
    if update_id in _seen_update_ids:
        return True
    _seen_update_ids[update_id] = now
    return False


@app.on_event('startup')
async def startup():
    global _http_client
    if not config.BOT_TOKEN:
        logger.warning('TELEGRAM_BOT_TOKEN not set')
    if not config.WEBHOOK_SECRET:
        logger.warning('TG_WEBHOOK_SECRET not set — /webhook will reject everything')
    _http_client = httpx.AsyncClient()
    asyncio.create_task(telegram_client.outbound_worker())


@app.get('/health')
async def health():
    return {'ok': True}


@app.post('/webhook')
async def webhook(request: Request, x_telegram_bot_api_secret_token: str = Header(default='')):
    if not config.WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail='webhook_secret_not_configured')
    if x_telegram_bot_api_secret_token != config.WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail='unauthorized')

    update = await request.json()
    if not update or _dedup_hit(update.get('update_id')):
        return {'ok': True}

    message = update.get('message') or {}
    text = message.get('text')
    if isinstance(text, str) and pairing.is_pair_command(text):
        try:
            await pairing.handle_pair_message(_http_client, message)
        except Exception:
            logger.exception('pair handling failed')
            raise HTTPException(status_code=500, detail='pair_failed')
        return {'ok': True}

    cq = update.get('callback_query')
    if cq:
        try:
            await callback.handle_callback_query(_http_client, cq)
        except Exception:
            logger.exception('callback_query handling failed')

    # /pair, 인라인 버튼 외 명령(공유 리드 배정/삭제/복구 등)은 최소 버전 범위 밖.
    return {'ok': True}


@app.post('/enqueue')
async def enqueue_endpoint(request: Request, x_enqueue_secret: str = Header(default='')):
    if config.ENQUEUE_SECRET and x_enqueue_secret != config.ENQUEUE_SECRET:
        raise HTTPException(status_code=401, detail='unauthorized')

    body = await request.json()
    method = body.get('method') or body.get('kind')
    payload = body.get('payload')
    if not method or not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail='method, payload required')

    chat_id = body.get('chat_id')
    if chat_id is not None and 'chat_id' not in payload:
        payload['chat_id'] = chat_id

    if body.get('awaitResult'):
        result = await telegram_client.dispatch_now(method, payload)
        return {'ok': True, 'result': result}

    telegram_client.enqueue(method, payload)
    return {'ok': True, 'queued': True}
