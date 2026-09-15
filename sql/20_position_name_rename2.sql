-- ================================================================
-- 20_position_name_rename2.sql — 직책명 변경 2차
-- ================================================================
-- 팀서기→지역부서기, 팀전도서기→지역부전서, 지역서기→수서기.
-- POSITION_CODE(코드값)는 그대로 두고 POSITION_NAME(화면 표시명)만 바꿈.
-- '지역서기'는 region_clerk/area_secretary 두 코드가 같은 이름을 공유해서
-- 둘 다 바뀜(어느 쪽도 현재 보유자 없어 영향 없음).
-- ================================================================

UPDATE POSITION_CODES SET POSITION_NAME = '지역부서기' WHERE POSITION_CODE = 'team_clerk';
UPDATE POSITION_CODES SET POSITION_NAME = '지역부전서' WHERE POSITION_CODE = 'team_mission_clerk';
UPDATE POSITION_CODES SET POSITION_NAME = '수서기'     WHERE POSITION_NAME = '지역서기';

COMMIT;
