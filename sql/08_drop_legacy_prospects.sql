-- ================================================================
-- 08_drop_legacy_prospects.sql — 구 PROSPECTS 계열 테이블 제거
-- ================================================================
-- 04_prospects.sql로 만든 PERSONAL_INFO/PROSPECTS/PROSPECT_HISTORY/
-- PROSPECT_TM_LOGS/PROSPECT_HABJAEYANG은 sarang 도메인(07_sarang.sql)으로
-- 대체됨. 실데이터가 0건이라(shed endpoint 포팅 테스트용으로만 만들었던
-- 테이블) 이관 없이 바로 제거. FK 의존관계상 자식 테이블부터 DROP.
--
-- USERS/ROLES/AUTH_CONFIGS(members 도메인으로 대체된 것들)는 team_4 실
-- 마이그레이션 데이터가 있어서 별도 전환 기간을 두고 나중에 한 번에 정리
-- 예정 — 여기서 같이 지우지 않음.
-- ================================================================

DROP TABLE PROSPECT_TM_LOGS PURGE;
DROP TABLE PROSPECT_HISTORY PURGE;
DROP TABLE PROSPECT_HABJAEYANG PURGE;
DROP TABLE PROSPECTS PURGE;
DROP TABLE PERSONAL_INFO PURGE;

COMMIT;
