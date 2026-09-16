# cron-router 파이썬 버전 — SCHEDULED_JOBS를 매 분 확인해 매칭되는 잡을 실행.
# services/cron-router(Node) 포팅. 실제 비즈니스 로직은 없음 — main(Django)의
# /internal/cron/* 를 호출만 하는 얇은 스케줄러.
import asyncio
import datetime
import logging
import time

import httpx
from fastapi import FastAPI, Header, HTTPException, Request

import config
import data_router_client as dr
import handlers
from runner import run_tick

logging.basicConfig(level=logging.INFO, format='%(asctime)s KST %(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger('cron_router')

app = FastAPI()
_http_client = None
_ticking = False  # self-tick과 외부 /tick이 겹쳐 쌓이지 않도록 하는 재진입 가드

_KST = datetime.timezone(datetime.timedelta(hours=9))


def _to_kst(value):
    """data_router가 UTC ISO 문자열(...Z)로 돌려주는 TIMESTAMP를 KST 문자열로 변환.
    /status, /tick 응답에서 시간대를 다시 계산 안 해도 되게 여기서 한 번에 맞춤."""
    if not value:
        return value
    dt = datetime.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return dt.astimezone(_KST).strftime('%Y-%m-%d %H:%M:%S KST')


def _ms_to_kst(ms):
    return datetime.datetime.fromtimestamp(ms / 1000, tz=_KST).strftime('%Y-%m-%d %H:%M:%S KST')


async def _guarded_run_tick(source):
    global _ticking
    if _ticking:
        logger.warning('tick skipped — previous tick still running (%s)', source)
        return {'skipped': True, 'fired': []}
    _ticking = True
    try:
        return await run_tick(_http_client)
    finally:
        _ticking = False


async def _self_tick_loop():
    # 다음 분(minute) 경계에 맞춰 첫 tick 시작 — :00, :10, :20... 정렬 유지.
    ms_to_next_minute = 60_000 - (int(time.time() * 1000) % 60_000)
    await asyncio.sleep(max(5, ms_to_next_minute / 1000))
    while True:
        try:
            result = await _guarded_run_tick('self')
            if result.get('fired'):
                logger.info('self-tick fired count=%s', len(result['fired']))
        except Exception:
            logger.exception('self-tick error')
        await asyncio.sleep(config.TICK_INTERVAL_MS / 1000)


@app.on_event('startup')
async def startup():
    global _http_client
    _http_client = httpx.AsyncClient()
    if config.SELF_TICK:
        asyncio.create_task(_self_tick_loop())


@app.get('/health')
async def health():
    return {
        'ok': True, 'service': 'cron_router', 'handlers': handlers.names(),
        'selfTick': config.SELF_TICK, 'tickIntervalMs': config.TICK_INTERVAL_MS,
    }


@app.post('/tick')
async def tick(request: Request, x_cron_secret: str = Header(default='')):
    if config.CRON_SECRET and x_cron_secret != config.CRON_SECRET:
        raise HTTPException(status_code=401, detail='unauthorized')
    result = await _guarded_run_tick('external')
    if 'tick' in result:
        result['tick'] = _ms_to_kst(result['tick'])
    return {'ok': True, **result}


@app.get('/status')
async def status():
    rows = await dr.query(
        _http_client,
        """SELECT JOB_ID, DESCRIPTION, CRON_EXPR, HANDLER, ENABLED,
                  LAST_RUN_AT, LAST_RUN_STATUS, LAST_RUN_FINISHED, LAST_RUN_DURATION, LAST_ERROR
             FROM SCHEDULED_JOBS WHERE DELETED_AT IS NULL ORDER BY JOB_ID""",
    )
    for r in rows:
        r['last_run_at'] = _to_kst(r.get('last_run_at'))
        r['last_run_finished'] = _to_kst(r.get('last_run_finished'))
    return {'jobs': rows, 'handlers': handlers.names()}
