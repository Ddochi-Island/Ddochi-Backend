-- ================================================================
-- 14_scheduled_jobs.sql — cron-router가 읽는 잡 스케줄 테이블 (신규)
-- ================================================================
-- 레거시 schema/ORACLE_SCHEMA.md의 SCHEDULED_JOBS 그대로 포팅 + 이 프로젝트
-- 공통 audit 컬럼(CREATED_BY 등은 시스템 잡이라 NULL 허용) 추가.
-- ================================================================

CREATE TABLE SCHEDULED_JOBS (
  JOB_ID             VARCHAR2(50 CHAR)            PRIMARY KEY,
  CRON_EXPR          VARCHAR2(50 CHAR)            NOT NULL,
  ENABLED            NUMBER(1)                    DEFAULT 1 NOT NULL CHECK (ENABLED IN (0,1)),
  DESCRIPTION        VARCHAR2(200 CHAR)           NOT NULL,
  PAYLOAD            CLOB,
  HANDLER            VARCHAR2(50 CHAR),
  LAST_RUN_AT        TIMESTAMP(6) WITH TIME ZONE,
  LAST_RUN_STATUS    VARCHAR2(10 CHAR)            CHECK (LAST_RUN_STATUS IN ('running','success','failed')),
  LAST_RUN_FINISHED  TIMESTAMP(6) WITH TIME ZONE,
  LAST_RUN_DURATION  NUMBER(10),
  LAST_ERROR         VARCHAR2(2000 CHAR),
  CREATED_AT         TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
  UPDATED_AT         TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
  UPDATED_BY         VARCHAR2(50 CHAR),
  DELETED_AT         TIMESTAMP(6) WITH TIME ZONE
);

COMMENT ON TABLE SCHEDULED_JOBS IS 'cron-router가 매칭해서 실행하는 잡 목록 — services/cron-router README 참고';
COMMENT ON COLUMN SCHEDULED_JOBS.JOB_ID IS 'handlers.js에 등록된 핸들러 키와 동일(예: sendProspectDashboard)';
COMMENT ON COLUMN SCHEDULED_JOBS.LAST_RUN_AT IS 'CAS 락 기준 컬럼 — 이 값보다 최신 매칭 시각일 때만 UPDATE 성공(리더 선출)';

INSERT INTO SCHEDULED_JOBS (JOB_ID, CRON_EXPR, ENABLED, DESCRIPTION, HANDLER)
VALUES ('sendProspectDashboard', '0 * * * *', 1, '찾기현황판 — 매 정각 새 메시지 발송 + 이전 삭제', 'sendProspectDashboard');

COMMIT;
