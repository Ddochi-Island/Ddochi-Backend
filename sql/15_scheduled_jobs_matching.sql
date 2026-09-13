-- ================================================================
-- 15_scheduled_jobs_matching.sql — 매칭현황판 정각 크론 잡 추가
-- ================================================================

INSERT INTO SCHEDULED_JOBS (JOB_ID, CRON_EXPR, ENABLED, DESCRIPTION, HANDLER)
VALUES ('sendMatchingDashboard', '0 * * * *', 1, '매칭현황판 — 매 정각 새 메시지 발송 + 이전 삭제', 'sendMatchingDashboard');

COMMIT;
