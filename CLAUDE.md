# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Django rebuild of `Ddochi/services/main` (the Express "main" API gateway, 90+ REST endpoints,
15 route categories). `data_router` (Go, talks to Oracle ADB) is carried over unchanged as the
sole database gateway — Django never connects to Oracle directly for business data.

Porting is happening one route at a time: `api/urls.py` already has all 237 endpoints wired up as
501 stubs mirroring the Express route files 1:1; only a few (e.g. `api/views/shed_users.py`) have
real logic. When porting a route, find its Express source under `Ddochi/services/main/src/routes/`
(the stub's docstring/TODO comment names the exact file) and preserve its request/response contract
exactly — external callers (e.g. the `shed` project) depend on the wire format, not the implementation.

## Commands

```bash
# env
source venv/bin/activate
pip install -r requirements.txt

# data_router (Go) — must be running before any endpoint that touches the DB works
docker compose up -d --build data_router      # dev Oracle (univdbdev_high), port 8080

# Django
python manage.py runserver 127.0.0.1:8000
python manage.py check
python manage.py migrate                      # sqlite only — see Architecture

# schema / data ops (all go through data_router, never direct Oracle)
python manage.py dr_ping                       # smoke-test data_router connectivity
python manage.py load_sql sql/<file>.sql        # run a DDL/seed file statement-by-statement
python manage.py import_prod_team <team_id>     # copy one team's USERS rows from prod → dev
```

No test suite yet.

## Architecture

**Two separate databases, deliberately:**
- `db.sqlite3` — Django's own internal tables (`admin`/`auth`/`sessions`) only. `config/settings.py`'s
  `DATABASES` points here, not at Oracle. This was a forced decision, not a style choice: the dev
  wallet's `ewallet.pem` is password-protected, so `django.db.backends.oracle` hangs on
  `runserver`'s migration check waiting on a PEM passphrase prompt on stdin. Don't repoint
  `DATABASES` at Oracle without solving that first.
- Oracle ADB (`univdbdev_high`, dev) — all real business data, reached exclusively through
  `data_router`'s `POST /v1/exec` wire protocol via `api/clients/data_router.py`'s
  `DataRouterClient` (`.query()` / `.exec()` / `.ping()`). Every view that touches data goes through
  this client — never add a second way to reach the DB.

**URL structure mirrors the Express app's three mount points**, preserved in `api/urls.py` as three
separate `urlpatterns` lists (`api_urlpatterns`, `internal_urlpatterns`, `internal_cron_urlpatterns`)
included in `config/urls.py` at `/api/`, `/internal/`, `/internal/cron/` respectively — matching
`services/main/src/index.js`'s router mounting exactly. `api/views/` has one module per Express route
file (`teams.js` → `teams.py`, etc.); where Express split one file into multiple routers with
different mount points (e.g. `telegramPair.js`, `sharedLeads.js`), the Django module is split the
same way (`telegram_pair.py` + `telegram_pair_internal.py`).

**Multi-method routes are dispatched inside one view**, not via duplicate `path()` entries — Django's
`path()` matches on URL only, not HTTP method, so two routes sharing a path (e.g. `GET`+`POST /ping`)
would silently shadow each other if registered separately. Follow the existing pattern
(`request.method` branch + 405 fallback) rather than adding a second `path()` for the same URL.

**`data_router_prod` in `docker-compose.yml`** is a second, read-only instance of the same Go binary
pointed at the *production* Oracle wallet (`Ddochi/wallet_v2`, port 8081) — used only for one-off
`import_prod_team`-style data migrations into the dev DB. Never call `.exec()`/write ops against it;
credentials for it are sourced from `Ddochi/.env` at container-start time, not stored in this repo's
own `.env`.

**Oracle NUMBER columns come back as strings** ("0"/"1") through `go-ora`, to preserve precision.
When checking a boolean-ish flag from a `DataRouterClient.query()` row, compare as string
(`row["x"] == "1"`), never `bool(row["x"])` — `bool("0")` is `True` in Python.

**`sql/*.sql`** holds the dev DB's schema, trimmed from the production schema
(`Ddochi/schema/ORACLE_SCHEMA.md`, `Ddochi/sql/`) on purpose — e.g. `USERS` keeps its `TEAM_ID`/
`AREA_ID` columns but drops the `REGIONS`/`TEAMS`/`AREAS` tables and their FKs entirely, since this
dev DB doesn't model the full org hierarchy. Don't assume the dev schema matches production 1:1;
check `sql/` before assuming a table/column exists.
