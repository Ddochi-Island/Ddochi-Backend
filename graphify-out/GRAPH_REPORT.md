# Graph Report - Ddochi_dev  (2026-08-31)

## Corpus Check
- Corpus is ~40,413 words - fits in a single context window. You may not need a graph.

## Summary
- 1113 nodes · 2045 edges · 64 communities (47 shown, 7 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 130 edges (avg confidence: 0.85)
- Token cost: 0 input · 80,066 output

## Community Hubs (Navigation)
- Object Storage Backends
- Queue & Resilience Tests
- HTTP Server & Middleware
- Sheets Route Stubs
- Teams Route Stubs
- Priority Queue & Worker Pool
- Cron Internal Routes
- Django data_router Client
- DB Executor
- Cron Internal Routes (cont.)
- Assets Route Stubs
- Assets Route Stubs (cont.)
- Daily Report Route Stubs
- Upload Queue
- Stats Route Stubs
- data_router Config & Idempotency
- Intake Sync Route Stubs
- Schedule Route Stubs
- Project Docs & Architecture Notes
- Dolyo Route Stubs
- TTL Cache
- Oracle DSN & Connection Pool
- Area Score Route Stubs
- Feedback Route Stubs
- Admin Users Route Stubs
- data_router Metrics
- Auth Route Stubs
- Telegram Pair Route Stubs
- URL Routing Wiring
- Board Route Stubs
- Signed Storage URLs
- Upload Queue Worker
- Locks Route Stubs
- Preview Route Stubs
- Shared Leads Claim Routes
- Architecture Rationale
- Admin Audit Log Route Stubs
- Ministry Route Stubs
- Storage Route Stubs
- Intake Webhook Routes
- Internal Telegram Routes
- Prayer Route Stubs
- Shared Leads Notify Routes
- Shed Report Routes
- Sheet Sync Routes
- data_router Design Notes
- Django App Config
- data_router Wire Protocol Notes
- Django CLI Entry
- CLAUDE.md Concepts
- ASGI Entry
- Django Settings
- WSGI Entry
- data_router Go Module

## God Nodes (most connected - your core abstractions)
1. `Job` - 25 edges
2. `Server` - 23 edges
3. `ObjectMeta` - 22 edges
4. `DataRouterClient` - 20 edges
5. `Task` - 19 edges
6. `main()` - 18 edges
7. `StorageHandlers` - 18 edges
8. `OCIBackend` - 18 edges
9. `Queue` - 18 edges
10. `New()` - 17 edges

## Surprising Connections (you probably didn't know these)
- `oracledb==4.0.2` --semantically_similar_to--> `Connection pool (database/sql + go-ora, wallet auth)`  [INFERRED] [semantically similar]
  requirements.txt → data_router/README.md
- `data_router (Go gateway service)` --conceptually_related_to--> `Oracle ADB univdbdev_high (dev)`  [AMBIGUOUS]
  data_router/README.md → CLAUDE.md
- `Django Rebuild of Express Main Gateway` --references--> `Django==6.1`  [EXTRACTED]
  CLAUDE.md → requirements.txt
- `python-decouple==3.8` --conceptually_related_to--> `config/settings.py DATABASES setting`  [INFERRED]
  requirements.txt → CLAUDE.md
- `oracledb==4.0.2` --conceptually_related_to--> `ewallet.pem passphrase blocks Oracle backend on runserver`  [INFERRED]
  requirements.txt → CLAUDE.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Request Handling Pipeline (queue to pool with cache/breaker/idem)** — data_router_readme_v1_exec_endpoint, data_router_readme_priority_queue, data_router_readme_connection_pool, data_router_readme_read_cache_singleflight, data_router_readme_circuit_breaker, data_router_readme_idempotency [EXTRACTED 1.00]
- **Two-Database Architecture (Django sqlite + Go-mediated Oracle)** — claude_db_sqlite3, claude_oracle_adb_univdbdev_high, claude_datarouterclient, data_router_readme_data_router [EXTRACTED 1.00]
- **Django Project Dependency Stack** — requirements_django, requirements_oracledb, requirements_gunicorn, requirements_cryptography, requirements_python_decouple [INFERRED 0.75]

## Communities (64 total, 7 thin omitted)

### Community 0 - "Object Storage Backends"
Cohesion: 0.05
Nodes (38): extFromContentType(), NewBlockBackend(), newKey(), readSidecar(), wrapCtx(), writeSidecar(), Decode(), EncodeBlock() (+30 more)

### Community 1 - "Queue & Resilience Tests"
Cohesion: 0.07
Nodes (65): main(), sweepLoop(), New(), TestClosedAllowsAll(), TestHalfOpenAfterDuration(), TestHalfOpenFailureReopens(), TestHalfOpenSingleTrialOnly(), TestHalfOpenSuccessClosesBreaker() (+57 more)

### Community 2 - "HTTP Server & Middleware"
Cohesion: 0.07
Nodes (34): Op, init(), L(), With(), isCachedQuery(), isWrite(), New(), validateRequest() (+26 more)

### Community 3 - "Sheets Route Stubs"
Cohesion: 0.06
Nodes (48): delete_import_status(), delete_sheet_config(), fetch_sheet_data(), get_sheet_configs(), get_sheet_prospects(), manage_sheet_config_order(), csrf_exempt, sheets.js 포팅 대상 — sheets 라우트 스텁 (구조만, 로직은 미구현). (+40 more)

### Community 4 - "Teams Route Stubs"
Cohesion: 0.06
Nodes (44): connect_telegram(), delete_path_config(), delete_tool_config(), get_auto_reject_config(), get_path_configs(), get_return_home_config(), get_scheduled_jobs(), get_team_areas() (+36 more)

### Community 5 - "Priority Queue & Worker Pool"
Cohesion: 0.10
Nodes (15): State, Priority, Breaker, deque, PriorityQueue, Task, laneIndex(), newDeque() (+7 more)

### Community 6 - "Cron Internal Routes"
Cohesion: 0.05
Nodes (37): cronInternal.js 포팅 대상 — cron_internal 라우트 스텁 (구조만, 로직은 미구현)., # TODO: services/main/src/routes/cronInternal.js 의 POST /send-feedback-…, # TODO: services/main/src/routes/cronInternal.js 의 POST /send-matching-…, # TODO: services/main/src/routes/cronInternal.js 의 POST /update-matching-…, # TODO: services/main/src/routes/cronInternal.js 의 POST /send-return-home 포팅, # TODO: services/main/src/routes/cronInternal.js 의 POST /sync-pii-hash 포팅, # TODO: services/main/src/routes/cronInternal.js 의 POST /ttl-pii-hash 포팅, # TODO: services/main/src/routes/cronInternal.js 의 POST /update-sheet-dashboard… (+29 more)

### Community 7 - "Django data_router Client"
Cohesion: 0.10
Nodes (19): DataRouterClient, DataRouterError, _rows_to_dicts(), Command, BaseCommand, Command, BaseCommand, Command (+11 more)

### Community 8 - "DB Executor"
Cohesion: 0.12
Nodes (29): Statement, ErrInfo, Meta, Request, Response, NowMeta(), detectColumnKinds(), errInfo() (+21 more)

### Community 9 - "Cron Internal Routes (cont.)"
Cohesion: 0.05
Nodes (37): broadcast_status(), logs(), csrf_exempt, send_activity_coord(), send_activity_report(), send_checkin(), send_current_schedule(), send_feedback_dashboard() (+29 more)

### Community 10 - "Assets Route Stubs"
Cohesion: 0.06
Nodes (35): assets.js 포팅 대상 — assets 라우트 스텁 (구조만, 로직은 미구현)., # TODO: services/main/src/routes/assets.js 의 POST /clone-row 포팅, # TODO: services/main/src/routes/assets.js 의 POST /get-center-assets 포팅, # TODO: services/main/src/routes/assets.js 의 POST /submit-habjaeyang-new 포팅, # TODO: services/main/src/routes/assets.js 의 POST /habjaeyang-dup-resolve 포팅, # TODO: services/main/src/routes/assets.js 의 POST /shed-call-status 포팅, # TODO: services/main/src/routes/assets.js 의 POST /shed-presence-leave 포팅, # TODO: services/main/src/routes/assets.js 의 POST /shed-call-start 포팅 (+27 more)

### Community 11 - "Assets Route Stubs (cont.)"
Cohesion: 0.06
Nodes (35): cancel_shed_habjaeyang(), clone_row(), delete_log(), edit_match(), get_assets(), get_center_assets(), get_matching_history(), get_shed_prospects() (+27 more)

### Community 12 - "Daily Report Route Stubs"
Cohesion: 0.09
Nodes (32): batch_update_executions(), daily_report(), daily_report_add_reg_entry(), daily_report_get(), daily_report_list_names(), daily_report_reflections(), daily_report_search_reg(), get_audit_logs() (+24 more)

### Community 13 - "Upload Queue"
Cohesion: 0.11
Nodes (13): deque, Queue, laneIndex(), newDeque(), newJob(), sync.Cond, sync.Mutex, deque (+5 more)

### Community 14 - "Stats Route Stubs"
Cohesion: 0.09
Nodes (30): get_comprehensive_stats(), get_personal_stats(), get_stats_password(), get_telegram_goals(), get_week_start_dow(), get_weekly_record(), my_archive(), my_goal() (+22 more)

### Community 15 - "data_router Config & Idempotency"
Cohesion: 0.14
Nodes (22): Breaker, Cache, HTTP, Idempotency, Limits, Queue, Storage, Worker (+14 more)

### Community 16 - "Intake Sync Route Stubs"
Cohesion: 0.11
Nodes (26): intake_assign_manager(), intake_delete_config(), intake_delete_row(), intake_dup_resolve(), intake_events(), intake_list_configs(), intake_list_prospects(), intake_save_config() (+18 more)

### Community 17 - "Schedule Route Stubs"
Cohesion: 0.11
Nodes (24): activity_schedule_get(), activity_schedule_save(), get_semester_schedule(), csrf_exempt, schedule.js 포팅 대상 — schedule 라우트 스텁 (구조만, 로직은 미구현)., # TODO: services/main/src/routes/schedule.js 의 POST /save-semester-schedule 포팅, # TODO: services/main/src/routes/schedule.js 의 POST /activity-schedule/get 포팅, # TODO: services/main/src/routes/schedule.js 의 POST /activity-schedule/save 포팅 (+16 more)

### Community 18 - "Project Docs & Architecture Notes"
Cohesion: 0.10
Nodes (24): api/clients/data_router.py, config/settings.py DATABASES setting, DataRouterClient (.query()/.exec()/.ping()), db.sqlite3 (Django internal DB), Django Rebuild of Express Main Gateway, ewallet.pem passphrase blocks Oracle backend on runserver, Express main API Gateway (legacy, Ddochi/services/main), Oracle ADB univdbdev_high (dev) (+16 more)

### Community 19 - "Dolyo Route Stubs"
Cohesion: 0.12
Nodes (22): add_dolyo_action(), delete_dolyo(), delete_dolyo_action(), dolyo_approval(), dolyo_match_result(), get_dolyo_list(), csrf_exempt, dolyo.js 포팅 대상 — dolyo 라우트 스텁 (구조만, 로직은 미구현). (+14 more)

### Community 20 - "TTL Cache"
Cohesion: 0.12
Nodes (15): cachedResult, entry, sentinelErr, Cache, Key(), New(), TestEvictionAtCap(), TestGetSetExpiry() (+7 more)

### Community 21 - "Oracle DSN & Connection Pool"
Cohesion: 0.16
Nodes (15): BuildConnString(), isIdentChar(), parseDescriptor(), ParseTNS(), splitTNSEntries(), stripTNSCommentsAndWS(), contains(), TestParseTNSAgainstRealWallet() (+7 more)

### Community 22 - "Area Score Route Stubs"
Cohesion: 0.13
Nodes (20): area_score_area_add(), area_score_area_detail(), area_score_area_remove_last(), area_score_mission_complete(), area_score_today(), area_score_toggle(), area_score_unlock_requests(), area_score_unlock_requests_id_complete() (+12 more)

### Community 23 - "Feedback Route Stubs"
Cohesion: 0.16
Nodes (16): feedback_slots_book(), feedback_slots_cancel(), feedback_slots_create(), feedback_slots_delete(), feedback_slots_list(), feedback_slots_pass_list(), feedback_slots_result(), csrf_exempt (+8 more)

### Community 24 - "Admin Users Route Stubs"
Cohesion: 0.18
Nodes (14): admin_users_bulk_update(), admin_users_create(), admin_users_list(), admin_users_meta(), admin_users_swap_teams(), admin_users_update(), csrf_exempt, adminUsers.js 포팅 대상 — admin_users 라우트 스텁 (구조만, 로직은 미구현). (+6 more)

### Community 25 - "data_router Metrics"
Cohesion: 0.21
Nodes (5): Registry, New(), sync/atomic.Int64, Counter, Gauge

### Community 26 - "Auth Route Stubs"
Cohesion: 0.21
Nodes (12): admin_unlock(), auth_config_get(), auth_config_save(), login(), csrf_exempt, auth.js 포팅 대상 — auth 라우트 스텁 (구조만, 로직은 미구현)., # TODO: services/main/src/routes/auth.js 의 POST /refresh 포팅, # TODO: services/main/src/routes/auth.js 의 POST /admin-unlock 포팅 (+4 more)

### Community 27 - "Telegram Pair Route Stubs"
Cohesion: 0.21
Nodes (12): csrf_exempt, telegramPair.js 포팅 대상 — telegram_pair 라우트 스텁 (구조만, 로직은 미구현)., # TODO: services/main/src/routes/telegramPair.js 의 POST /telegram-pair/status 포팅, # TODO: services/main/src/routes/telegramPair.js 의 POST /telegram-…, # TODO: services/main/src/routes/telegramPair.js 의 POST /telegram/link-me 포팅, # TODO: services/main/src/routes/telegramPair.js 의 POST /telegram-pair/cancel 포팅, # TODO: services/main/src/routes/telegramPair.js 의 POST /telegram-pair/start 포팅, telegram_link_me() (+4 more)

### Community 28 - "URL Routing Wiring"
Cohesion: 0.20
Nodes (7): health(), main(Express) 라우트 구조를 그대로 옮긴 URL 스캐폴딩. /api, /internal, /internal/cron 3개 목록으로…, csrf_exempt, telegramPair.js 포팅 대상 — telegram_pair_internal 라우트 스텁 (구조만, 로직은 미구현)., # TODO: services/main/src/routes/telegramPair.js 의 POST /telegram/pair-complete…, telegram_pair_complete(), URL configuration for config project. The `urlpatterns` list routes URLs to…

### Community 29 - "Board Route Stubs"
Cohesion: 0.24
Nodes (10): board_manage(), comment_manage(), post_interact(), post_manage(), csrf_exempt, board.js 포팅 대상 — board 라우트 스텁 (구조만, 로직은 미구현)., # TODO: services/main/src/routes/board.js 의 POST /post/manage 포팅, # TODO: services/main/src/routes/board.js 의 POST /post/interact 포팅 (+2 more)

### Community 30 - "Signed Storage URLs"
Cohesion: 0.35
Nodes (8): SignBlockToken(), flipChar(), TestExpiredTokenRejected(), TestMalformedTokenRejected(), TestSignVerifyRoundTrip(), TestTamperedTokenRejected(), TestWrongSecretRejected(), VerifyBlockToken()

### Community 31 - "Upload Queue Worker"
Cohesion: 0.31
Nodes (5): NewWorker(), removeIfExists(), sync.WaitGroup, Queue, Worker

### Community 32 - "Locks Route Stubs"
Cohesion: 0.28
Nodes (8): lock_acquire(), lock_heartbeat(), lock_release(), csrf_exempt, locks.js 포팅 대상 — locks 라우트 스텁 (구조만, 로직은 미구현)., # TODO: services/main/src/routes/locks.js 의 POST /lock/heartbeat 포팅, # TODO: services/main/src/routes/locks.js 의 POST /lock/release 포팅, # TODO: services/main/src/routes/locks.js 의 POST /lock/acquire 포팅

### Community 33 - "Preview Route Stubs"
Cohesion: 0.28
Nodes (8): preview_activity_coord(), preview_activity_report(), preview_current_schedule(), csrf_exempt, preview.js 포팅 대상 — preview 라우트 스텁 (구조만, 로직은 미구현)., # TODO: services/main/src/routes/preview.js 의 POST /preview-current-schedule 포팅, # TODO: services/main/src/routes/preview.js 의 POST /preview-activity-report 포팅, # TODO: services/main/src/routes/preview.js 의 POST /preview-activity-coord 포팅

### Community 34 - "Shared Leads Claim Routes"
Cohesion: 0.28
Nodes (8): csrf_exempt, sharedLeads.js 포팅 대상 — shared_leads_claim 라우트 스텁 (구조만, 로직은 미구현)., # TODO: services/main/src/routes/sharedLeads.js 의 POST /telegram/restore-…, # TODO: services/main/src/routes/sharedLeads.js 의 POST /telegram/claim-shared-…, # TODO: services/main/src/routes/sharedLeads.js 의 POST /telegram/delete-shared-…, telegram_claim_shared_lead(), telegram_delete_shared_lead(), telegram_restore_shared_lead()

### Community 35 - "Architecture Rationale"
Cohesion: 0.25
Nodes (8): api/urls.py (237 endpoints, 501 stubs), api/views/shed_users.py, config/urls.py, Ddochi/services/main/src/routes/, Multi-method routes dispatched inside one view, services/main/src/index.js router mounting, shed project (external caller, wire-format dependent), Three-mount-point URL structure (api/internal/internal_cron)

### Community 36 - "Admin Audit Log Route Stubs"
Cohesion: 0.33
Nodes (6): cron_logs(), get_admin_audit_log(), csrf_exempt, adminAuditLog.js 포팅 대상 — admin_audit_log 라우트 스텁 (구조만, 로직은 미구현)., # TODO: services/main/src/routes/adminAuditLog.js 의 GET /cron-logs 포팅, # TODO: services/main/src/routes/adminAuditLog.js 의 POST /get-admin-audit-log 포팅

### Community 37 - "Ministry Route Stubs"
Cohesion: 0.33
Nodes (6): manage_ministry_categories(), manage_notification_times(), csrf_exempt, ministry.js 포팅 대상 — ministry 라우트 스텁 (구조만, 로직은 미구현)., # TODO: services/main/src/routes/ministry.js 의 POST /manage-notification-times…, # TODO: services/main/src/routes/ministry.js 의 POST /manage-ministry-categories…

### Community 38 - "Storage Route Stubs"
Cohesion: 0.33
Nodes (6): csrf_exempt, storage.js 포팅 대상 — storage 라우트 스텁 (구조만, 로직은 미구현)., # TODO: services/main/src/routes/storage.js 의 GET /storage/image 포팅, # TODO: services/main/src/routes/storage.js 의 POST /storage/upload 포팅, storage_image(), storage_upload()

### Community 39 - "Intake Webhook Routes"
Cohesion: 0.40
Nodes (4): intake_drive_notify(), csrf_exempt, intakeWebhook.js 포팅 대상 — intake_webhook 라우트 스텁 (구조만, 로직은 미구현)., # TODO: services/main/src/routes/intakeWebhook.js 의 POST /intake/drive-notify 포팅

### Community 40 - "Internal Telegram Routes"
Cohesion: 0.40
Nodes (4): csrf_exempt, internalTelegram.js 포팅 대상 — internal_telegram 라우트 스텁 (구조만, 로직은 미구현)., # TODO: services/main/src/routes/internalTelegram.js 의 POST /telegram/callback…, telegram_callback()

### Community 41 - "Prayer Route Stubs"
Cohesion: 0.40
Nodes (4): csrf_exempt, prayer.js 포팅 대상 — prayer 라우트 스텁 (구조만, 로직은 미구현)., # TODO: services/main/src/routes/prayer.js 의 POST /submit-prayer 포팅, submit_prayer()

### Community 42 - "Shared Leads Notify Routes"
Cohesion: 0.40
Nodes (4): csrf_exempt, sharedLeads.js 포팅 대상 — shared_leads_notify 라우트 스텁 (구조만, 로직은 미구현)., # TODO: services/main/src/routes/sharedLeads.js 의 POST /shared-leads/notify 포팅, shared_leads_notify()

### Community 43 - "Shed Report Routes"
Cohesion: 0.40
Nodes (4): csrf_exempt, shedReport.js 포팅 대상 — shed_report 라우트 스텁 (구조만, 로직은 미구현)., # TODO: services/main/src/routes/shedReport.js 의 GET /shed/report 포팅, shed_report()

### Community 44 - "Sheet Sync Routes"
Cohesion: 0.40
Nodes (4): csrf_exempt, sheetSync.js 포팅 대상 — sheet_sync 라우트 스텁 (구조만, 로직은 미구현)., # TODO: services/main/src/routes/sheetSync.js 의 POST /sheet-sync 포팅, sheet_sync()

### Community 45 - "data_router Design Notes"
Cohesion: 0.50
Nodes (4): POST_ATTACHMENTS storage columns (SCHEMA_DELTA.sql), Schema-agnostic schema versioning design, Storage endpoints (OCI Object Storage + Block-Volume fallback), V3.13 TEAM/AREA snapshot columns + BEFORE INSERT trigger

### Community 47 - "data_router Wire Protocol Notes"
Cohesion: 0.67
Nodes (3): Circuit breaker, Stable error.code table, Priority queue (high/normal/low, bounded + admission control)

## Ambiguous Edges - Review These
- `Oracle ADB univdbdev_high (dev)` → `data_router (Go gateway service)`  [AMBIGUOUS]
  data_router/README.md · relation: conceptually_related_to

## Knowledge Gaps
- **21 isolated node(s):** `github.com/redesign2/services/data_router`, `cachedResult`, `ctxKey`, `StorageHandlers`, `Express main API Gateway (legacy, Ddochi/services/main)` (+16 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 366 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Oracle ADB univdbdev_high (dev)` and `data_router (Go gateway service)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `Server` connect `HTTP Server & Middleware` to `Object Storage Backends`, `Priority Queue & Worker Pool`, `data_router Config & Idempotency`, `TTL Cache`, `Oracle DSN & Connection Pool`, `data_router Metrics`?**
  _High betweenness centrality (0.014) - this node is a cross-community bridge._
- **Why does `main()` connect `Queue & Resilience Tests` to `Object Storage Backends`, `HTTP Server & Middleware`, `Priority Queue & Worker Pool`, `DB Executor`, `data_router Config & Idempotency`, `TTL Cache`, `Oracle DSN & Connection Pool`, `data_router Metrics`, `Upload Queue Worker`?**
  _High betweenness centrality (0.014) - this node is a cross-community bridge._
- **What connects `github.com/redesign2/services/data_router`, `cachedResult`, `ctxKey` to the rest of the system?**
  _21 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Object Storage Backends` be split into smaller, more focused modules?**
  _Cohesion score 0.05378151260504202 - nodes in this community are weakly interconnected._
- **Should `Queue & Resilience Tests` be split into smaller, more focused modules?**
  _Cohesion score 0.07099099099099099 - nodes in this community are weakly interconnected._
- **Should `HTTP Server & Middleware` be split into smaller, more focused modules?**
  _Cohesion score 0.07122153209109731 - nodes in this community are weakly interconnected._