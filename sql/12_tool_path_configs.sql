-- ================================================================
-- 12_tool_path_configs.sql — 섭외도구/섭외경로 설정 (신규)
-- ================================================================
-- 레거시 TOOLS_CONFIGS/PATH_CONFIGS 포팅. 레거시는 TEAM_ID가 TEAMS(TEAM_ID) FK였지만
-- 이 프로젝트 dev 스키마엔 TEAMS 테이블 자체가 없음(04_prospects.sql 등과 동일한 이유로
-- REGIONS/TEAMS/AREAS 생략) — TEAM_ID는 MEMBER_AFFILIATION_HISTORIES.REGION_CODE와
-- 같은 코드값을 그대로 담는 평문 컬럼으로 FK 없이 둠(BROADCAST_SETTINGS와 동일 패턴).
-- REGION_ID(레거시의 지역 스코프)는 이 프로젝트가 단일 지역만 다뤄서 뺌.
-- ================================================================

CREATE TABLE TOOLS_CONFIGS (
  TOOL_CONFIG_ID  VARCHAR2(30 CHAR)            PRIMARY KEY,
  TEAM_ID         VARCHAR2(20 CHAR),
  AUTHOR_SABUN    VARCHAR2(50 CHAR)            NOT NULL,
  NAME            VARCHAR2(100 CHAR)           NOT NULL,
  DESCRIPTION     VARCHAR2(1000 CHAR),
  CATEGORY        VARCHAR2(50 CHAR),
  ORDER_KEY       NUMBER(5)                    DEFAULT 999 NOT NULL,
  CREATED_AT      TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
  UPDATED_AT      TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
  CREATED_BY      VARCHAR2(50 CHAR)            NOT NULL,
  UPDATED_BY      VARCHAR2(50 CHAR)            NOT NULL,
  DELETED_AT      TIMESTAMP(6) WITH TIME ZONE,
  CONSTRAINT FK_TC_AUTHOR FOREIGN KEY (AUTHOR_SABUN) REFERENCES MEMBERS(MEMBER_ID)
);
CREATE INDEX IX_TC_TEAM ON TOOLS_CONFIGS (TEAM_ID, ORDER_KEY);

COMMENT ON TABLE  TOOLS_CONFIGS            IS '섭외도구 설정 — 합재양 작성 폼의 "섭외도구" 드롭다운';
COMMENT ON COLUMN TOOLS_CONFIGS.TEAM_ID    IS 'NULL=공용(전체 팀), 값 있으면 그 팀 전용 — MEMBER_AFFILIATION_HISTORIES.REGION_CODE와 동일한 코드값(FK 없음)';

CREATE TABLE PATH_CONFIGS (
  PATH_CONFIG_ID  VARCHAR2(30 CHAR)            PRIMARY KEY,
  TEAM_ID         VARCHAR2(20 CHAR),
  AUTHOR_SABUN    VARCHAR2(50 CHAR)            NOT NULL,
  NAME            VARCHAR2(200 CHAR)           NOT NULL,
  DESCRIPTION     VARCHAR2(1000 CHAR),
  ORDER_KEY       NUMBER(5)                    DEFAULT 999 NOT NULL,
  ON_OFF          VARCHAR2(10 CHAR)            DEFAULT 'online' NOT NULL CHECK (ON_OFF IN ('online','offline')),
  CREATED_AT      TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
  UPDATED_AT      TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
  CREATED_BY      VARCHAR2(50 CHAR)            NOT NULL,
  UPDATED_BY      VARCHAR2(50 CHAR)            NOT NULL,
  DELETED_AT      TIMESTAMP(6) WITH TIME ZONE,
  CONSTRAINT FK_PC_AUTHOR FOREIGN KEY (AUTHOR_SABUN) REFERENCES MEMBERS(MEMBER_ID)
);

COMMENT ON TABLE  PATH_CONFIGS         IS '섭외경로 설정 — 합재양 작성 폼의 "섭외경로" 드롭다운. 현재 관리 화면(PathManagementModal.vue)엔 팀 구분 UI가 없어 항상 공용(TEAM_ID NULL)으로 저장됨';
COMMENT ON COLUMN PATH_CONFIGS.ON_OFF  IS '온/오프라인 구분 — 일일보고 화면 등에서 씀';

COMMIT;
