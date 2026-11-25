-- 수지역(전 지역) 매칭현황판 발송 시각: 06·09·12·15·18·21·23·24(=00)시 (2026-11-25 사용자 요청)
UPDATE SCHEDULED_JOBS SET CRON_EXPR = '0 0,6,9,12,15,18,21,23 * * *',
       DESCRIPTION = '수지역 매칭현황판 — 06·09·12·15·18·21·23·24시 새 메시지 발송 + 이전 삭제'
 WHERE JOB_ID = 'sendMatchingDashboardAll';

COMMIT;
