-- ================================================================
-- 25_district_groups.sql — 반(구역 3~4개 묶음) + 반장 직책
-- ================================================================
-- 반장은 전도팀장 아래, 구역장 위. 반장의 실제 관리 범위는 DISTRICT_GROUPS.LEADER_MEMBER_ID
-- 기준이고, MEMBER_POSITION_MAPPINGS의 group_lead 행은 직책 표시/겸직용(반장 지정 API가 자동으로 맞춤).
-- DISTRICT_CODES는 같은 지역의 DISTRICT_CODE 콤마 목록(예: '1,2,3').
-- ================================================================

INSERT INTO POSITION_CODES (POSITION_CODE, POSITION_NAME, PERMISSIONS, SCOPE, CREATED_BY, UPDATED_BY)
VALUES ('group_lead', '반장', '["view_group"]', 'team', 'SYSTEM', 'SYSTEM');

CREATE TABLE DISTRICT_GROUPS (
  GROUP_ID          VARCHAR2(50 CHAR)            PRIMARY KEY,
  REGION_CODE       VARCHAR2(20 CHAR)            NOT NULL,
  GROUP_NAME        VARCHAR2(50 CHAR)            NOT NULL,
  DISTRICT_CODES    VARCHAR2(200 CHAR)           NOT NULL,
  LEADER_MEMBER_ID  VARCHAR2(50 CHAR),
  CREATED_AT        TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
  UPDATED_AT        TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
  CREATED_BY        VARCHAR2(50 CHAR)            NOT NULL,
  UPDATED_BY        VARCHAR2(50 CHAR)            NOT NULL,
  DELETED_AT        TIMESTAMP(6) WITH TIME ZONE,
  CONSTRAINT FK_DG_LEADER FOREIGN KEY (LEADER_MEMBER_ID) REFERENCES MEMBERS(MEMBER_ID)
);

CREATE INDEX IX_DG_REGION ON DISTRICT_GROUPS (REGION_CODE);
CREATE INDEX IX_DG_LEADER ON DISTRICT_GROUPS (LEADER_MEMBER_ID);

COMMENT ON TABLE DISTRICT_GROUPS IS '반 — 한 지역 안에서 구역 3~4개를 묶은 단위. 반장(LEADER_MEMBER_ID)이 반 전체 구역을 관리';

COMMIT;
