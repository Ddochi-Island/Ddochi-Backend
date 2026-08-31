# data_router

Single Go-based gateway between caller services and the OCI Autonomous Database (`univdb1_tp`).
The DB has exactly one connected service: this one. Everyone else talks to the router over HTTP/JSON.

## Why

- **Stability first.** A bounded priority queue keeps the DB from being overrun; backpressure surfaces as `503 queue_full` instead of cascading timeouts. A circuit breaker fails fast when the DB is unhealthy. Idempotency-Key makes write retries safe.
- **Throughput second.** A 1–2s read cache + singleflight collapses repeated dashboard polls into a single DB round-trip. Worker concurrency = DB pool size, so the pool runs hot but never thrashes.

## Architecture

```
caller → POST /v1/exec
       │
       ▼
   ┌─────────────┐  ┌─────────────────┐  ┌──────────┐
   │ HTTP server │─▶│ priority queue  │─▶│  worker  │─▶ Oracle ADB
   │ (auth, ID,  │  │  high/norm/low  │  │   pool   │
   │  validate)  │  │  bounded + RR   │  │  N gor.  │
   └─────────────┘  └─────────────────┘  └──────────┘
                              ▲                 │
                              │                 ▼
                       per-caller cap     ┌─────────────────┐
                       lane reservations  │ TTL cache + SF  │
                                          │ idem store      │
                                          │ breaker         │
                                          └─────────────────┘
```

## Wire protocol

`POST /v1/exec`, `Content-Type: application/json`, `Authorization: Bearer <INTERNAL_API_TOKEN>`.

```json
{
  "caller": "tel_router",
  "op": "query",                       // query | exec | tx | proc | ping
  "stmt": {
    "sql": "SELECT * FROM USERS WHERE TEAM_ID = :1 AND DELETED_AT IS NULL",
    "args": ["team_3"],
    "fetch_limit": 1000
  },
  "priority": "normal",                // high | normal | low
  "cache_ttl_ms": 1500,                // 0 = no cache; only honored for op=query
  "idempotency_key": "uuid-v4",        // only honored for writes
  "timeout_ms": 5000
}
```

For `op: "tx"`, omit `stmt` and pass `statements: [{sql, args}, ...]` — executed in order in one transaction.

### Response shape

```json
{
  "status": "ok",                      // ok | error | rejected
  "columns": ["ID","NAME"],            // op=query
  "rows": [[1,"alice"], [2,"bob"]],    // op=query
  "truncated": false,                  // true iff fetch_limit was hit
  "rows_affected": 0,                  // op=exec|tx|proc
  "meta": {
    "request_id": "...",
    "queued_ms": 3,
    "exec_ms": 11,
    "total_ms": 14,
    "cache_hit": false,
    "coalesced": false,
    "lane": "normal",
    "server_time": "2026-04-30T..."
  }
}
```

### Column type handling

The router projects driver-returned values into JSON-friendly shapes:

| Oracle type | JSON output |
|---|---|
| `NUMBER` | number (int or float depending on scale) |
| `VARCHAR2` / `NVARCHAR2` / `CLOB` (small) | string |
| `DATE` / `TIMESTAMP [WITH TIME ZONE]` | string, RFC3339Nano UTC |
| `RAW` / `BLOB` | base64 string |
| `JSON` (Oracle 21c+ native) | **native JSON** — passed through as a JSON value, not a base64 string. Invalid JSON bytes fall back to base64 so data is never lost. |

So a query returning a `broadcast_settings.config JSON` column comes back as `[1, {"key": "value"}]` directly — no client-side decode step.

Errors carry a stable `error.code` so callers can branch without parsing messages:

| Code | HTTP | Retryable |
|------|------|-----------|
| `bad_request` | 400 | no |
| `unauthorized` | 401 | no |
| `payload_too_large` | 413 | no |
| `queue_full` | 503 | yes — back off |
| `breaker_open` | 502 | yes — back off |
| `timeout` | 504 | yes |
| `db_unavailable` | 502 | yes |
| `oracle_error` | 502 | depends on `error.retryable` (true for ORA-00060/-00054/-08177/etc.) |
| `shutting_down` | 503 | yes — try another instance |
| `internal` | 500 | no |

### Other endpoints

- `GET /healthz` — liveness, always 200.
- `GET /readyz` — 200 only when DB pool is healthy and breaker isn't open.
- `GET /metrics` — Prometheus text format.
- `GET /stats` — JSON snapshot for human dashboards.

### Storage endpoints

The router is also the gateway to OCI Object Storage (primary) with a local Block-Volume fallback that kicks in when the free-tier 10 GiB is approaching its limit. Once an object is stored, its **id encodes the backend** (`o:bucket/key` for OCI, `b:shard/uuid.ext` for block) so reads can be dispatched without a DB round-trip and the same id remains valid forever.

| Endpoint | Purpose |
|---|---|
| `POST /v1/storage/upload` | multipart or octet-stream upload. Returns `{meta: {id, backend, size, sha256, ...}}`. Caller stores `id` in DB. |
| `GET /v1/storage/url?id=<id>&ttl_seconds=60` | Returns a short-lived download URL. For OCI ids it's a fresh PAR; for block ids it's a HMAC-signed router URL. Caller services GET the URL directly. |
| `GET /v1/storage/meta?id=<id>` | metadata only. |
| `DELETE /v1/storage/object?id=<id>` | delete. Caller is responsible for the DB row. |
| `GET /v1/storage/blob/{token}` | unauthenticated (token-authorized) blob download for block backend. Used by the URL minted above; not called directly by services. |
| `GET /v1/storage/usage` | capacity report + which backend the next upload will land in. |

Notes:

- **Backend choice is permanent per object.** No migration. Existing objects keep working regardless of where the threshold sits.
- **Free-tier sizing**: default threshold is 8 GiB (`STORAGE_THRESHOLD_BYTES`). At 8 GiB used, new uploads land in `BLOCK_STORAGE_ROOT`.
- **Usage polling**: OCI bucket size is polled every `STORAGE_USAGE_REFRESH_EVERY` (60s default). Between polls, in-process counter adjustments keep the picker honest.
- **Auth on OCI VM**: prefer `OS_AUTH_MODE=instance_principal` — no key files to rotate.

## Schema versioning

data_router is **schema-agnostic by design**. The only SQL the binary
issues itself is `SELECT 1 FROM DUAL` for health checks; everything else
flows through `/v1/exec` from caller services. That means schema bumps
in V3 do not require a router redeploy.

The router currently runs alongside V3.13. Two implications callers
should know about:

- **TEAM/AREA snapshot columns (V3.13)**. 14 event/log tables (`POSTS`,
  `POST_COMMENTS`, `POST_REACTIONS`, `DAILY_REPORTS`, `PROSPECT_HISTORY`,
  ...) gained `SNAP_TEAM_ID` + `SNAP_AREA_ID NOT NULL`. A BEFORE INSERT
  trigger auto-fills these from `USERS.TEAM_ID` / `AREA_ID` keyed by
  whichever sabun column the table uses (`AUTHOR_SABUN` for community,
  `SABUN` for daily ops, `TARGET_SABUN` for `DAILY_REPORT_HISTORY`). So
  caller `INSERT` statements **don't** specify SNAP columns and just
  work — but the sabun the caller binds **must exist in `USERS`** or
  the trigger raises `NO_DATA_FOUND` and the row is rejected.

- **`POST_ATTACHMENTS` (this service)**. Storage metadata columns
  (`STORAGE_ID`, `BACKEND`, `OBJECT_KEY`, `BUCKET_NAME`, `BYTE_SIZE`,
  `CONTENT_TYPE`, `SHA256`) live in [SCHEMA_DELTA.sql](./SCHEMA_DELTA.sql).
  Already applied on `univdb1_tp`. Independent of V3.13 — the table
  isn't in the SNAP-affected list. Callers store the storage `id`
  returned from `POST /v1/storage/upload` in `STORAGE_ID` (or the
  legacy `URL` column).

If V3.14+ adds tables / columns, the router still needs no change —
caller services adapt their SQL and the gateway just transports.

## Operational design notes

### Priority queue

3 lanes (high/normal/low) drained in order. Admission control reserves slots so a flood in the low lane can never push out a high-priority request:

- low admitted only if `total < cap - HighReserved - NormalReserved`
- normal admitted only if `total < cap - HighReserved`
- high admitted only if `total < cap`

Plus a per-caller cap so one runaway caller can't take over a lane.

### Read cache + singleflight

Default off; callers opt in per-request with `cache_ttl_ms`. The router caps at `CACHE_MAX_TTL` (default **5s**) — anything larger gets silently truncated. `CACHE_DEFAULT_TTL` is 1s.

When enabled and 100 callers hit the same SQL+args within 1s, exactly one DB round-trip happens — the rest ride on the singleflight leader's result. The cache key is `sha256(op || sql || JSON(args))`.

The HTTP layer also fast-paths cache hits *before* enqueueing, so polling dashboards don't even occupy queue slots.

**Caller-side TTL policy (Phase 14-B, 2026-05-11)**:

| 데이터 특성 | TTL | 예 |
|---|---|---|
| **Hot path** — auth 미들웨어 / 화면 진입마다 호출되는 lookup | `1_000` (1s) | USERS by sabun, TEAMS 목록, BOARDS, MINISTRY_CATEGORIES, SHEET_CONFIGS (user), TOOLS_CONFIGS, WEEKLY_PLAN_TEMPLATES |
| **Low-churn config** — admin 변경 화면, auth metadata | `5_000` (5s) | PASSKEY_HASH, ACCESS_TTL/REFRESH_TTL, SHEET_CONFIGS (admin), SCHEDULED_JOBS |
| **변경 잦은 도메인 (prospects/dailyReports/posts)** | **cache 안 걸기** (`cacheTtlMs` 생략 또는 0) | prospect 목록, 일일보고 작성, 게시판 글 |
| **ERP 통계 풀스캔** | `1_500` (1.5s) — ERP 의 기존 표준 | ERP query.js, templates.js |

**Router-side cap 5s** — caller 측 low-churn 정책 5s 와 일치. caller 가 부주의하게 더 큰 값 (예: 60s) 보내도 5s 로 절삭하는 safety net — stale window 가 5s 를 절대 못 넘게 보장.

**Reasoning** — 사용자 팀/권한 변경 후 stale window 가 길면 보안/UX 문제. 변경 잦은 도메인 (prospect 등)은 cache 가 오히려 stale 위험. 1초 hot path 면 100명 동시 화면 진입 시 ATP 부하 줄이면서도 변경 반영 즉시성 확보. router cap 5s 가 절대 상한.

### Idempotency

For `exec`/`tx`/`proc`, a caller-supplied `idempotency_key` is cached with the response for `IDEMPOTENCY_WINDOW` (default 10m). Concurrent duplicates wait on the leader rather than racing to the DB. A leader whose request *fails* releases the slot so the next retry can run fresh.

### Circuit breaker

Sliding window of recent samples. Trips on `>=BREAKER_FAILURE_RATIO` (default 60%) infrastructural failures within `BREAKER_WINDOW` samples (default 50). Application-level Oracle errors (unique violation, missing table) do NOT feed the breaker — they're caller bugs, not DB outages.

When open, all incoming requests get `502 breaker_open` immediately. After `BREAKER_OPEN_DURATION`, the breaker goes half-open and lets exactly one trial through.

### Connection pool

`database/sql` over `github.com/sijms/go-ora/v2` (pure Go, no Oracle Instant Client). Wallet auth via `cwallet.sso`. The pool sets `MaxOpenConns=30/MaxIdleConns=10/ConnMaxLifetime=30m` by default — tune to your ADB shape.

Health check pings `SELECT 1 FROM DUAL` every `DB_HEALTHCHECK_INTERVAL`; a single failed probe flips `/readyz` to 503 immediately.

### Graceful shutdown

On SIGTERM/SIGINT:
1. HTTP server stops accepting new requests.
2. Queue closes — pending tasks fail with `shutting_down`; in-flight tasks keep running.
3. Workers drain.
4. DB pool closes.

Bound by `HTTP_SHUTDOWN_TO` (default 25s).

## Run

VM 배포는 루트 `docker-compose.yml` + 루트 `.env` 가 모든 env 를 주입하므로 별도 파일 X.

로컬 standalone dev:
```
# repo root 의 .env 에서 ORACLE_PASSWORD/INTERNAL_API_TOKEN 등을 환경에 export 하거나
# 직접 export ORACLE_PASSWORD=...
go run ./cmd/data_router
```

고급 튜닝 노브 (`QUEUE_HIGH_RESERVED`, `WORKER_TICK_INTERVAL`, `CACHE_DEFAULT_TTL` 등) 는 `internal/config/config.go` 참조. 보통 default 그대로 둠.

Or build:

```
go build -o bin/data_router ./cmd/data_router
./bin/data_router
```

## Smoke test

```bash
TOK=$(grep INTERNAL_API_TOKEN .env | cut -d= -f2)

# ping
curl -s localhost:8080/v1/exec \
  -H "Authorization: Bearer $TOK" \
  -d '{"caller":"smoke","op":"ping"}' | jq

# cached query
curl -s localhost:8080/v1/exec \
  -H "Authorization: Bearer $TOK" \
  -d '{"caller":"smoke","op":"query","priority":"normal","cache_ttl_ms":1500,
       "stmt":{"sql":"SELECT COUNT(*) FROM USERS"}}' | jq

# exec with idempotency
curl -s localhost:8080/v1/exec \
  -H "Authorization: Bearer $TOK" \
  -d '{"caller":"smoke","op":"exec","priority":"high",
       "idempotency_key":"7c8a-...",
       "stmt":{"sql":"UPDATE USERS SET UPDATED_AT=SYSTIMESTAMP WHERE SABUN=:1","args":["10001"]}}' | jq
```

## Tuning checklist

| Symptom | Knob |
|---|---|
| `queue_full` under steady load | bump `QUEUE_CAPACITY`, then `WORKER_CONCURRENCY` + `DB_MAX_OPEN_CONNS` together |
| High `queued_ms` (>500ms p95) | bump `WORKER_CONCURRENCY` + `DB_MAX_OPEN_CONNS` together |
| ADB sessions exhausted | drop `DB_MAX_OPEN_CONNS` to fit the tier limit |
| Same dashboard polled repeatedly | callers add `cache_ttl_ms: 1000` (hot path 정책) |
| Caller monopolizing queue | tighten `QUEUE_PER_CALLER_LIMIT` |
| Frequent breaker trips on healthy DB | raise `BREAKER_FAILURE_RATIO` or `BREAKER_MIN_SAMPLES` |
