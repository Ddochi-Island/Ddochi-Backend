-- ================================================================
-- 17_dashboard_cron_windows.sql — 정각 발송 시간대 제한
-- ================================================================
-- 일일보고: 06~22시만(레거시 22시 업무일 마감과 동일 시각).
-- 찾기/매칭현황판: 06~23시만.
-- ================================================================

UPDATE SCHEDULED_JOBS SET CRON_EXPR = '0 6-22 * * *' WHERE JOB_ID = 'sendStats';
UPDATE SCHEDULED_JOBS SET CRON_EXPR = '0 6-23 * * *' WHERE JOB_ID = 'sendProspectDashboard';
UPDATE SCHEDULED_JOBS SET CRON_EXPR = '0 6-23 * * *' WHERE JOB_ID = 'sendMatchingDashboard';

COMMIT;
