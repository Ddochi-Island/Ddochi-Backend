-- ================================================================
-- 02_roles.sql — ROLES (dev DB, 축소판)
-- ================================================================
-- 원본: Ddochi/sql/01_organization.sql 의 ROLES.
-- REGION_ID 컬럼 제거 — 실제 쿼리 어디서도 REGION_ID로 필터링하지 않음
-- (SCOPE 우선순위 정렬만 쓰임). REGIONS 테이블 자체도 안 만들었으니 FK도
-- 애초에 성립 불가. SCHEMA_VERSION 은 USERS 때와 동일한 이유로 제거.
-- ================================================================

CREATE TABLE ROLES (
  ROLE_ID         VARCHAR2(30 CHAR)            PRIMARY KEY,
  NAME            VARCHAR2(30 CHAR)            NOT NULL,
  SCOPE           VARCHAR2(10 CHAR)            NOT NULL CHECK (SCOPE IN ('region','team','global')),
  PERMISSIONS     CLOB                         NOT NULL,
  CREATED_AT      TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
  UPDATED_AT      TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
  CREATED_BY      VARCHAR2(20 CHAR)            NOT NULL,
  UPDATED_BY      VARCHAR2(20 CHAR)            NOT NULL,
  DELETED_AT      TIMESTAMP(6) WITH TIME ZONE,
  CONSTRAINT CK_ROLES_PERMS_JSON CHECK (PERMISSIONS IS JSON)
);

COMMENT ON TABLE  ROLES              IS '직책 마스터 (지역장/팀장 등). dev DB, REGION_ID 없음';
COMMENT ON COLUMN ROLES.SCOPE        IS 'global > region > team 순으로 대표 직책 선택 시 우선순위';
COMMENT ON COLUMN ROLES.PERMISSIONS  IS 'JSON 배열. 예: ["admin","region_staff"]. 인가 판정의 실제 근거';
