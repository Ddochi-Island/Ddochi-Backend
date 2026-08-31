-- ================================================================
-- 01_users.sql — USERS (dev DB, 축소판)
-- ================================================================
-- 원본: Ddochi/sql/01_organization.sql + 29_users_merge_roles_goals.sql
--       + 30_org_hardening.sql 를 합친 최종 컬럼 구성.
-- REGIONS/TEAMS/AREAS 테이블은 만들지 않음 — TEAM_ID/AREA_ID 컬럼은
-- 그대로 두되 FK 제거 (평문 문자열 값으로만 사용).
-- ================================================================

CREATE TABLE USERS (
  SABUN           VARCHAR2(20 CHAR)            PRIMARY KEY,
  NAME            VARCHAR2(50 CHAR)            NOT NULL,
  TEAM_ID         VARCHAR2(30 CHAR)            NOT NULL,
  AREA_ID         VARCHAR2(30 CHAR)            NOT NULL,
  GMAIL           VARCHAR2(255 CHAR),
  TELEGRAM_ID     VARCHAR2(20 CHAR),
  STATUS          VARCHAR2(10 CHAR)            DEFAULT 'active' NOT NULL
                  CHECK (STATUS IN ('active','inactive','leave')),
  ROLE_IDS        CLOB                         CHECK (ROLE_IDS IS NULL OR ROLE_IDS IS JSON),
  GOALS           CLOB                         CHECK (GOALS IS NULL OR GOALS IS JSON),
  CREATED_AT      TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
  UPDATED_AT      TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
  CREATED_BY      VARCHAR2(20 CHAR)            NOT NULL,
  UPDATED_BY      VARCHAR2(20 CHAR)            NOT NULL,
  DELETED_AT      TIMESTAMP(6) WITH TIME ZONE
);

CREATE UNIQUE INDEX UX_USERS_TG ON USERS (
  CASE WHEN TELEGRAM_ID IS NOT NULL THEN TELEGRAM_ID END
);

COMMENT ON TABLE  USERS              IS '사용자 — PK = 사번. dev DB, REGIONS/TEAMS/AREAS FK 없음';
COMMENT ON COLUMN USERS.SABUN        IS 'PK. 사번 (예: ''12345678'', ''SYSTEM''=시스템 시드)';
COMMENT ON COLUMN USERS.TEAM_ID      IS 'FK 없는 평문 팀 식별자';
COMMENT ON COLUMN USERS.AREA_ID      IS 'FK 없는 평문 구역 식별자';
COMMENT ON COLUMN USERS.TELEGRAM_ID  IS '텔레그램 numeric chat_id. 부분 UNIQUE 인덱스';
COMMENT ON COLUMN USERS.STATUS       IS 'active=재직 / inactive=시스템 시드/비활성 / leave=휴직';
COMMENT ON COLUMN USERS.ROLE_IDS     IS '직책 ROLE_ID JSON 배열. 예: ["areaLeader"]';
COMMENT ON COLUMN USERS.GOALS        IS '개인 목표 JSON. {"weekly":{"dm":..,"qr":..,"nf":..,"mh":..,"ec":..,"sc":..,"tec":..,"tsc":..}}';

-- 시스템 사번 시드 — SHED_USERS 등 조회에서 WHERE SABUN != 'SYSTEM' 로 제외.
INSERT INTO USERS (SABUN, NAME, TEAM_ID, AREA_ID, STATUS, CREATED_BY, UPDATED_BY)
VALUES ('SYSTEM', '시스템', '0', '0', 'inactive', 'SYSTEM', 'SYSTEM');

COMMIT;
