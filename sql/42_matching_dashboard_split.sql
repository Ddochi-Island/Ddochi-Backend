-- 매칭현황판 발송을 둘로 나눔(2026-11-25 사용자 요청): 지역판은 매시간(06~23시), 수지역(전 지역)판은 3시간마다(07~22시)
-- 같은 핸들러에 payload로 대상 방을 거름(cron_internal.send_matching_dashboard). 백엔드 배포 뒤 적용할 것
UPDATE SCHEDULED_JOBS SET CRON_EXPR = '0 6-23 * * *', PAYLOAD = '{"exclude": ["수지역"]}',
       DESCRIPTION = '지역 매칭현황판 — 매 정각(06~23시) 새 메시지 발송 + 이전 삭제'
 WHERE JOB_ID = 'sendMatchingDashboard';
INSERT INTO SCHEDULED_JOBS (JOB_ID, CRON_EXPR, ENABLED, DESCRIPTION, HANDLER, PAYLOAD)
VALUES ('sendMatchingDashboardAll', '0 7-22/3 * * *', 1, '수지역 매칭현황판 — 3시간마다(07~22시) 새 메시지 발송 + 이전 삭제',
        'sendMatchingDashboard', '{"only": ["수지역"]}');

COMMIT;
