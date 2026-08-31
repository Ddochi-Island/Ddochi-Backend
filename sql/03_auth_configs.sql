-- ================================================================
-- 03_auth_configs.sql — AUTH_CONFIGS (dev DB, 축소판)
-- ================================================================
-- 원본: Ddochi/sql/07_system_erp.sql 의 AUTH_CONFIGS.
-- REGION_ID 는 PK로 유지 — 모든 쿼리가 WHERE REGION_ID=:1 로 필터링하므로
-- ROLES.REGION_ID(미사용)와 다름. REGIONS 테이블이 없으니 FK만 제거.
-- SCHEMA_VERSION 은 USERS/ROLES 때와 동일한 이유로 제거.
-- ================================================================

CREATE TABLE AUTH_CONFIGS (
  REGION_ID       VARCHAR2(30 CHAR)            PRIMARY KEY,
  PASSKEY_HASH    VARCHAR2(64 CHAR)            NOT NULL,
  ACCESS_TTL      VARCHAR2(10 CHAR)            NOT NULL,
  REFRESH_TTL     VARCHAR2(10 CHAR)            NOT NULL,
  CREATED_AT      TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
  UPDATED_AT      TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
  CREATED_BY      VARCHAR2(20 CHAR)            NOT NULL,
  UPDATED_BY      VARCHAR2(20 CHAR)            NOT NULL,
  DELETED_AT      TIMESTAMP(6) WITH TIME ZONE
);

COMMENT ON TABLE  AUTH_CONFIGS             IS '지역별 로그인 패스키 + JWT TTL 표시값. dev DB, FK 없음';
COMMENT ON COLUMN AUTH_CONFIGS.PASSKEY_HASH IS '공유 패스키의 sha256 hex 해시';
COMMENT ON COLUMN AUTH_CONFIGS.ACCESS_TTL   IS '표시/설정용 — 실제 JWT 발급은 서버 부팅 시 JWT_ACCESS_TTL env로 고정, 이 값을 매 로그인마다 다시 읽지 않음';
COMMENT ON COLUMN AUTH_CONFIGS.REFRESH_TTL  IS '표시/설정용 — ACCESS_TTL과 동일한 이유로 실시간 반영 안 됨';
