-- ================================================================
-- 19_position_name_rename.sql — 직책명 변경
-- ================================================================
-- 임원→수지역장, 지역장→전도교관, 팀장→지역장, 팀전도교관→전도팀장.
-- POSITION_CODE(코드값)는 그대로 두고 POSITION_NAME(화면 표시명)만 바꿈 —
-- 권한 스코프(SCOPE)는 코드 기준이라 안 바뀜.
-- ================================================================

UPDATE POSITION_CODES SET POSITION_NAME = '수지역장' WHERE POSITION_CODE = 'executive';
UPDATE POSITION_CODES SET POSITION_NAME = '전도교관' WHERE POSITION_CODE = 'region_lead';
UPDATE POSITION_CODES SET POSITION_NAME = '지역장'   WHERE POSITION_CODE = 'team_lead';
UPDATE POSITION_CODES SET POSITION_NAME = '전도팀장' WHERE POSITION_CODE = 'team_evangelist';

COMMIT;
