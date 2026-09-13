-- ================================================================
-- 18_shed_union_jobs.sql — 135/246 연합 사쉐 대시보드 정각 크론 잡
-- ================================================================

INSERT INTO SCHEDULED_JOBS (JOB_ID, CRON_EXPR, ENABLED, DESCRIPTION, HANDLER)
VALUES ('sendShedUnifiedDashboard135', '0 6-23 * * *', 1, '135 연합 통합현황판 — 매 정각 새 메시지 발송 + 이전 삭제', 'sendShedUnifiedDashboard135');

INSERT INTO SCHEDULED_JOBS (JOB_ID, CRON_EXPR, ENABLED, DESCRIPTION, HANDLER)
VALUES ('sendShedUnifiedDashboard246', '0 6-23 * * *', 1, '246 연합 통합현황판 — 매 정각 새 메시지 발송 + 이전 삭제', 'sendShedUnifiedDashboard246');

INSERT INTO SCHEDULED_JOBS (JOB_ID, CRON_EXPR, ENABLED, DESCRIPTION, HANDLER)
VALUES ('sendShedTmDashboard135', '0 6-23 * * *', 1, '135 연합 TM현황 — 매 정각 새 메시지 발송 + 이전 삭제', 'sendShedTmDashboard135');

INSERT INTO SCHEDULED_JOBS (JOB_ID, CRON_EXPR, ENABLED, DESCRIPTION, HANDLER)
VALUES ('sendShedTmDashboard246', '0 6-23 * * *', 1, '246 연합 TM현황 — 매 정각 새 메시지 발송 + 이전 삭제', 'sendShedTmDashboard246');

INSERT INTO SCHEDULED_JOBS (JOB_ID, CRON_EXPR, ENABLED, DESCRIPTION, HANDLER)
VALUES ('sendShedSchedDashboard135', '0 6-23 * * *', 1, '135 연합 예약타임테이블 — 매 정각 새 메시지 발송 + 이전 삭제', 'sendShedSchedDashboard135');

INSERT INTO SCHEDULED_JOBS (JOB_ID, CRON_EXPR, ENABLED, DESCRIPTION, HANDLER)
VALUES ('sendShedSchedDashboard246', '0 6-23 * * *', 1, '246 연합 예약타임테이블 — 매 정각 새 메시지 발송 + 이전 삭제', 'sendShedSchedDashboard246');

COMMIT;
