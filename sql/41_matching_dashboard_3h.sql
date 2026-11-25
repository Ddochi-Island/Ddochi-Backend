-- 매칭현황판 정각 새 발송을 1시간 → 3시간 간격으로(07·10·13·16·19·22시, 2026-11-25 사용자 요청)
-- 결과입력·재가 같은 이벤트 때 기존 메시지 수정은 그대로. 되돌리기: CRON_EXPR = '0 6-23 * * *'
UPDATE SCHEDULED_JOBS SET CRON_EXPR = '0 7-22/3 * * *', DESCRIPTION = '매칭현황판 — 3시간마다(07~22시) 새 메시지 발송 + 이전 삭제'
 WHERE JOB_ID = 'sendMatchingDashboard';

COMMIT;
