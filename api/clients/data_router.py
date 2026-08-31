# data_router 의 POST /v1/exec wire protocol 얇은 클라이언트.
# 대응: services/main/src/clients/dataRouterClient.js (동일 프로토콜, 동일 계약).
# 계약: data_router/internal/api/types.go
from __future__ import annotations

import requests
from django.conf import settings


class DataRouterError(Exception):
    def __init__(self, message, code=None, ora_code=0, retryable=False, http_status=None):
        super().__init__(message)
        self.code = code
        self.ora_code = ora_code
        self.retryable = retryable
        self.http_status = http_status


class DataRouterClient:
    def __init__(self, url=None, token=None, caller=None, timeout_ms=None):
        self.url = (url or settings.DATA_ROUTER_URL).rstrip('/')
        self.token = token if token is not None else settings.DATA_ROUTER_TOKEN
        self.caller = caller or settings.DATA_ROUTER_CALLER
        self.timeout_ms = timeout_ms or settings.DATA_ROUTER_TIMEOUT_MS

    def query(self, sql, args=None, fetch_limit=0, priority='normal', cache_ttl_ms=0, timeout_ms=0):
        body = {
            'caller': self.caller,
            'op': 'query',
            'stmt': {'sql': sql, 'args': args or [], 'fetch_limit': fetch_limit},
            'priority': priority,
            'cache_ttl_ms': cache_ttl_ms,
            'timeout_ms': timeout_ms,
        }
        data = self._post(body)
        return _rows_to_dicts(data.get('columns', []), data.get('rows', []))

    def query_one(self, sql, args=None, **opts):
        rows = self.query(sql, args, fetch_limit=1, **opts)
        return rows[0] if rows else None

    def exec(self, sql, args=None, priority='normal', timeout_ms=0, idempotency_key=None):
        body = {
            'caller': self.caller,
            'op': 'exec',
            'stmt': {'sql': sql, 'args': args or []},
            'priority': priority,
            'timeout_ms': timeout_ms,
        }
        if idempotency_key:
            body['idempotency_key'] = idempotency_key
        return self._post(body).get('rows_affected', 0)

    def ping(self):
        return self._post({'caller': self.caller, 'op': 'ping'})

    def _post(self, body):
        headers = {'Authorization': f'Bearer {self.token}'} if self.token else {}
        try:
            res = requests.post(
                f'{self.url}/v1/exec',
                json=body,
                headers=headers,
                timeout=self.timeout_ms / 1000,
            )
        except requests.RequestException as e:
            raise DataRouterError(f'data_router transport: {e}', code='transport', retryable=True) from e

        payload = res.json() if res.content else {}
        if payload.get('status') == 'ok':
            return payload
        info = payload.get('error') or {}
        raise DataRouterError(
            info.get('message') or f'data_router {payload.get("status") or res.status_code}',
            code=info.get('code') or f'http_{res.status_code}',
            ora_code=info.get('ora_code', 0),
            retryable=info.get('retryable', False),
            http_status=res.status_code,
        )


# go-ora 는 NUMBER 컬럼을 string("0"/"1")으로 돌려준다 (precision 보존).
# boolean flag 변환 시 `bool(r["x"])` 금지 — "0"도 truthy. `r["x"] == "1"` 사용할 것.
def _rows_to_dicts(columns, rows):
    lc = [str(c).lower() for c in columns]
    return [dict(zip(lc, row)) for row in rows]
