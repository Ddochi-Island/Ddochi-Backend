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


def _ms_to_next_boundary():
    """다음 TICK_INTERVAL 경계(:00, :10, :20…)까지 남은 ms. 매번 벽시계로 다시 맞춰서 정각 발송이
    컨테이너 시작 시각만큼 밀리지 않게 함 — 전엔 첫 tick만 분 경계에 맞추고 이후 고정 10분이라 배포 시각에 따라
    매시 :08 같은 데서 발송됐음(2026-10-05). UTC 경계 = KST 경계(9시간은 10분의 배수)."""
    interval = config.TICK_INTERVAL_MS
    return interval - (int(time.time() * 1000) % interval)


async def _self_tick_loop():
    # 시작 직후 한 번 — 정각 직전·직후 재시작으로 놓친 발송(최근 1시간, LOOKBACK)을 다음 경계까지 기다리지 않고 바로 보냄.
    # 같은 회차 중복 발송은 run_tick의 LAST_RUN_AT CAS가 막음.
    first = True
    while True:
        if not first:
            await asyncio.sleep(max(1, _ms_to_next_boundary()) / 1000 + 0.5)  # 경계 0.5초 뒤 — 시계 오차로 직전에 깨는 것 방지
        first = False
        try:
            result = await _guarded_run_tick('self')
            if result.get('fired'):
                logger.info('self-tick fired count=%s', len(result['fired']))
        except Exception:
            logger.exception('self-tick error')


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
