# 한 번의 tick — services/cron-router/src/cron/runner.js 포팅.
# SCHEDULED_JOBS에서 매칭된 잡을 CAS(compare-and-swap)로 선점한 뒤 핸들러 실행.
import asyncio
import datetime
import json
import logging
import time

import config
import data_router_client as dr
import handlers
from cron_match import find_recent_match

logger = logging.getLogger('cron_router.runner')

HANDLER_TIMEOUT_S = 45.0


def _iso(ms):
    return datetime.datetime.fromtimestamp(ms / 1000, tz=datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'


def _to_ms(dt_str):
    if not dt_str:
        return 0
    # DataRouterClient는 TIMESTAMP를 ISO 문자열로 돌려줌.
    dt_str = dt_str.replace('Z', '+00:00')
    return int(datetime.datetime.fromisoformat(dt_str).timestamp() * 1000)


async def run_tick(http_client, now_ms=None):
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    jobs = await dr.query(
        http_client,
        """SELECT JOB_ID, DESCRIPTION, CRON_EXPR, HANDLER, PAYLOAD, LAST_RUN_AT
             FROM SCHEDULED_JOBS WHERE ENABLED = 1 AND DELETED_AT IS NULL""",
    )

    fired = []
    for job in jobs:
        last_run_ms = _to_ms(job.get('last_run_at'))
        matched_at = find_recent_match(job['cron_expr'], now_ms, last_run_ms, config.LOOKBACK_WINDOW_MS)
        if not matched_at:
            continue
        if last_run_ms >= matched_at:
            continue

        match_iso = _iso(matched_at)
        claimed = await dr.exec_(
            http_client,
            """UPDATE SCHEDULED_JOBS
                  SET LAST_RUN_AT = TO_TIMESTAMP_TZ(:1, 'YYYY-MM-DD"T"HH24:MI:SS.FF3"Z"'),
                      LAST_RUN_STATUS = 'running', UPDATED_AT = SYSTIMESTAMP, UPDATED_BY = 'cron_router'
                WHERE JOB_ID = :2 AND ENABLED = 1 AND DELETED_AT IS NULL
                  AND (LAST_RUN_AT IS NULL
                       OR LAST_RUN_AT < TO_TIMESTAMP_TZ(:1, 'YYYY-MM-DD"T"HH24:MI:SS.FF3"Z"'))""",
            [match_iso, job['job_id']],
        )
        if not claimed:
            logger.debug('cas missed job_id=%s', job['job_id'])
            continue

        handler = handlers.get(job['handler'])
        if not handler:
            logger.warning('unknown handler job_id=%s handler=%s', job['job_id'], job['handler'])
            continue

        try:
            payload = json.loads(job['payload']) if job.get('payload') else {}
        except (TypeError, ValueError):
            payload = {}
        ctx = {'http': http_client, 'now': matched_at, 'job_id': job['job_id'], 'payload': payload}

        t0 = time.monotonic()
        ok, err_msg, result = True, None, None
        try:
            result = await asyncio.wait_for(handler(ctx), timeout=HANDLER_TIMEOUT_S)
        except Exception as e:
            ok = False
            err_msg = str(e)
            logger.error('job fail job_id=%s error=%s', job['job_id'], err_msg)
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        try:
            await dr.exec_(
                http_client,
                """UPDATE SCHEDULED_JOBS
                      SET LAST_RUN_STATUS = :1, LAST_RUN_FINISHED = SYSTIMESTAMP,
                          LAST_RUN_DURATION = :2, LAST_ERROR = :3,
                          UPDATED_AT = SYSTIMESTAMP, UPDATED_BY = 'cron_router'
                    WHERE JOB_ID = :4""",
                ['success' if ok else 'failed', elapsed_ms, err_msg or '', job['job_id']],
            )
        except Exception as e:
            logger.warning('finish update failed job_id=%s error=%s', job['job_id'], e)

        fired.append({'job_id': job['job_id'], 'ok': ok, 'ms': elapsed_ms, 'result': result, 'error': err_msg})
        if ok:
            logger.info('job ok job_id=%s ms=%s', job['job_id'], elapsed_ms)

    return {'tick': now_ms, 'total': len(jobs), 'fired': fired}
