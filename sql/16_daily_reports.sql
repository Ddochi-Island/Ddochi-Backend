-- ================================================================
-- 16_daily_reports.sql — 일일보고 제출 테이블 + 정각 통계 크론 잡
-- ================================================================
-- Ddochi/services/main/src/routes/dailyReport.js의 DAILY_REPORTS 포팅.
-- 레거시 대비 축소: SABUN→MEMBER_ID, AREAS 없어서 SNAP_DISTRICT_CODE로 대체,
-- FLYER_COUNT/MOOD/REFLECTION/DAILY_REPORT_LEAVES는 현재 프론트가 안 보내서 제외.
-- ================================================================

CREATE TABLE DAILY_REPORTS (
  REPORT_DATE          DATE                          NOT NULL,
  MEMBER_ID            VARCHAR2(50 CHAR)             NOT NULL,
  AUTHOR_MEMBER_ID      VARCHAR2(50 CHAR)             NOT NULL,
  ACTIVITY             VARCHAR2(20 CHAR)             NOT NULL CHECK (ACTIVITY IN ('none','online','offline','offlineSearch')),
  TALK_COUNT            NUMBER(5)                     DEFAULT 0 NOT NULL,
  DM_COUNT               NUMBER(5)                     DEFAULT 0 NOT NULL,
  QR_COUNT                NUMBER(5)                     DEFAULT 0 NOT NULL,
  ONLINE_INTAKE_COUNT      NUMBER(5)                     DEFAULT 0 NOT NULL,
  PROMO_LIST            CLOB,
  REG_LIST              CLOB,
  IS_FINAL              NUMBER(1)                     DEFAULT 0 NOT NULL CHECK (IS_FINAL IN (0,1)),
  SNAP_REGION_CODE       VARCHAR2(20 CHAR),
  SNAP_DISTRICT_CODE      VARCHAR2(20 CHAR),
  SUBMITTED_AT           TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
  CREATED_AT             TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
  UPDATED_AT             TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
  CREATED_BY             VARCHAR2(50 CHAR)             NOT NULL,
  UPDATED_BY             VARCHAR2(50 CHAR)             NOT NULL,
  DELETED_AT             TIMESTAMP(6) WITH TIME ZONE,
  CONSTRAINT PK_DAILY_REPORTS PRIMARY KEY (REPORT_DATE, MEMBER_ID),
  CONSTRAINT FK_DR_MEMBER FOREIGN KEY (MEMBER_ID)        REFERENCES MEMBERS(MEMBER_ID),
  CONSTRAINT FK_DR_AUTHOR FOREIGN KEY (AUTHOR_MEMBER_ID) REFERENCES MEMBERS(MEMBER_ID)
);

CREATE INDEX IX_DR_REGION_DATE ON DAILY_REPORTS (SNAP_REGION_CODE, REPORT_DATE);

COMMENT ON TABLE DAILY_REPORTS IS '일일보고 제출 — 개인 활동 기록(톡/DM/QR/온라인유입) + 제출 시점 소속 스냅샷';
COMMENT ON COLUMN DAILY_REPORTS.AUTHOR_MEMBER_ID IS '실제로 제출한 사람 — 팀장 등이 대리 제출 가능해서 MEMBER_ID와 다를 수 있음';
COMMENT ON COLUMN DAILY_REPORTS.PROMO_LIST IS 'JSON 배열 [{school,path,tool}] — 오늘 홍보한 곳';
COMMENT ON COLUMN DAILY_REPORTS.REG_LIST IS 'JSON 배열 [{name,verbalManFix,result}] — 구두 등록/만픽 메모';
COMMENT ON COLUMN DAILY_REPORTS.SNAP_REGION_CODE   IS '제출 시점 소속 지역(구 팀) 스냅샷 — MEMBER_AFFILIATION_HISTORIES.REGION_CODE';
COMMENT ON COLUMN DAILY_REPORTS.SNAP_DISTRICT_CODE IS '제출 시점 소속 구역 스냅샷 — MEMBER_AFFILIATION_HISTORIES.DISTRICT_CODE';

INSERT INTO SCHEDULED_JOBS (JOB_ID, CRON_EXPR, ENABLED, DESCRIPTION, HANDLER)
VALUES ('sendStats', '0 * * * *', 1, '일일보고 — 매 정각 새 메시지 발송 + 이전 삭제', 'sendStats');

COMMIT;
