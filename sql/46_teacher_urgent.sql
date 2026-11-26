-- 교사 급구 — 하루 3번(09·13·18시) 수지역 teacherUrgentChatId 방에 합재양 카드 + 목록(2026-11-27 사용자 결정). 백엔드 배포 뒤 적용
INSERT INTO SCHEDULED_JOBS (JOB_ID, CRON_EXPR, ENABLED, DESCRIPTION, HANDLER, PAYLOAD)
VALUES ('sendTeacherUrgent', '0 9,13,18 * * *', 1, '교사 급구 — 09·13·18시 합재양 카드 + 교사 미정 매칭 목록', 'sendTeacherUrgent', NULL);

COMMIT;
