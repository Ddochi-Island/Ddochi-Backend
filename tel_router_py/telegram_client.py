# 텔레그램 Bot API 발송 담당 — 큐 하나 + 워커 하나, per-chat 1초 쿨다운만 지원(우선순위 없음)
# ponytail: 우선순위 큐/멀티봇/스냅샷 영속성은 원본 tel_router에 있지만 여기선 뺐음.
#           main 서버가 실시간 발송량이 늘어나면 그때 추가.
import asyncio
import logging

import httpx

import config

logger = logging.getLogger('tel_router.telegram')

PER_CHAT_COOLDOWN_S = 1.0

_queue = asyncio.Queue()
_last_sent_at = {}


def enqueue(method, payload):
    _queue.put_nowait({'method': method, 'payload': payload})


async def _call(client, method, payload):
    url = f'{config.TELEGRAM_API_BASE}/bot{config.BOT_TOKEN}/{method}'
    resp = await client.post(url, json=payload, timeout=10.0)
    if resp.status_code == 429:
        retry_after = (resp.json().get('parameters') or {}).get('retry_after', 1)
        await asyncio.sleep(retry_after)
        resp = await client.post(url, json=payload, timeout=10.0)
    return resp


async def _dispatch(client, method, payload):
    resp = await _call(client, method, payload)
    if resp.status_code >= 400:
        logger.error('%s failed status=%s body=%s', method, resp.status_code, resp.text)


async def dispatch_now(method, payload):
    """main(Django)이 결과(예: message_id)를 즉시 받아야 할 때 쓰는 동기 경로 —
    큐를 거치지 않고 바로 호출. per-chat 쿨다운도 적용 안 함(버튼 응답 등 저빈도 호출용)."""
    async with httpx.AsyncClient() as client:
        resp = await _call(client, method, payload)
        return resp.json()


async def outbound_worker():
    async with httpx.AsyncClient() as client:
        while True:
            item = await _queue.get()
            chat_id = item['payload'].get('chat_id')
            loop = asyncio.get_event_loop()
            wait = PER_CHAT_COOLDOWN_S - (loop.time() - _last_sent_at.get(chat_id, 0))
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                await _dispatch(client, item['method'], item['payload'])
            except Exception:
                logger.exception('dispatch failed method=%s', item['method'])
            _last_sent_at[chat_id] = asyncio.get_event_loop().time()
            _queue.task_done()
