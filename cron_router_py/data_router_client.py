# data_router POST /v1/exec 클라이언트 — Ddochi-Backend의 api/clients/data_router.py와 동일 계약.
# 별도 배포되는 서비스라 그 모듈을 직접 import하지 않고 최소 형태로 다시 구현.
import httpx

import config


def _rows_to_dicts(columns, rows):
    lc = [str(c).lower() for c in columns]
    return [dict(zip(lc, row)) for row in rows]


async def query(client, sql, args=None, fetch_limit=0):
    body = {
        'caller': config.DATA_ROUTER_CALLER,
        'op': 'query',
        'stmt': {'sql': sql, 'args': args or [], 'fetch_limit': fetch_limit},
    }
    data = await _post(client, body)
    return _rows_to_dicts(data.get('columns', []), data.get('rows', []))


async def query_one(client, sql, args=None):
    rows = await query(client, sql, args, fetch_limit=1)
    return rows[0] if rows else None


async def exec_(client, sql, args=None):
    body = {
        'caller': config.DATA_ROUTER_CALLER,
        'op': 'exec',
        'stmt': {'sql': sql, 'args': args or []},
    }
    data = await _post(client, body)
    return data.get('rows_affected', 0)


async def _post(client, body):
    headers = {'Authorization': f'Bearer {config.DATA_ROUTER_TOKEN}'} if config.DATA_ROUTER_TOKEN else {}
    resp = await client.post(f'{config.DATA_ROUTER_URL}/v1/exec', json=body, headers=headers, timeout=15.0)
    payload = resp.json() if resp.content else {}
    if payload.get('status') == 'ok':
        return payload
    info = payload.get('error') or {}
    raise RuntimeError(info.get('message') or f'data_router {payload.get("status") or resp.status_code}')
