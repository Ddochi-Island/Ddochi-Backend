-- ================================================================
-- 05_shed_extras.sql — Shed TM 워크보드 부속 테이블 (dev DB, 축소판)
-- ================================================================
-- USER_TM_SCRIPTS: Ddochi/sql/*.sql에 체크인된 마이그레이션이 없는 테이블
-- (스키마 드리프트). 2026-08-31 prod USER_TAB_COLUMNS/USER_CONS_COLUMNS를
-- 직접 조회해 확정한 실제 컬럼/PK 그대로. FK 없음(prod도 USERS FK 없음).
--
-- GACHA_COUNTS: Ddochi/sql/61_gacha_counts.sql 그대로(이미 FK 없음).
-- BROADCAST_SETTINGS: Ddochi/sql/04_telegram.sql 기준, TEAMS FK만 제거.
-- ================================================================

CREATE TABLE USER_TM_SCRIPTS (
  SABUN         VARCHAR2(120 CHAR)           NOT NULL,
  SCRIPT_TYPE   VARCHAR2(80 CHAR)            DEFAULT 'tm' NOT NULL,
  SCRIPT_MODE   VARCHAR2(80 CHAR)            DEFAULT 'default' NOT NULL,
  SCRIPT_TEXT   CLOB,
  UPDATED_AT    TIMESTAMP(6)                 DEFAULT SYSTIMESTAMP NOT NULL,
  CONSTRAINT PK_UTS PRIMARY KEY (SABUN, SCRIPT_TYPE)
);

COMMENT ON TABLE USER_TM_SCRIPTS IS '사번별 TM 스크립트(개인화 멘트). prod 실측 스키마 그대로, FK 없음';

CREATE TABLE GACHA_COUNTS (
    SABUN       VARCHAR2(20)  NOT NULL,
    COUNT       NUMBER(2)     DEFAULT 0 NOT NULL,
    UPDATED_AT  TIMESTAMP     DEFAULT SYSTIMESTAMP,
    CONSTRAINT PK_GACHA_COUNTS PRIMARY KEY (SABUN)
);

COMMENT ON TABLE GACHA_COUNTS IS '선한 양치기 인도권 가챠 카운트 (티엠자 사번별 누적 비당첨 횟수)';

CREATE TABLE BROADCAST_SETTINGS (
  TEAM_ID         VARCHAR2(30 CHAR)            NOT NULL,
  BROADCAST_TYPE  VARCHAR2(30 CHAR)            NOT NULL,
  ENABLED         NUMBER(1)                    DEFAULT 0 NOT NULL CHECK (ENABLED IN (0,1)),
  BROADCAST_MODE  VARCHAR2(10 CHAR)            NOT NULL CHECK (BROADCAST_MODE IN ('none','time','hourly','event')),
  TIMES           CLOB,
  CONFIG          CLOB,
  LAST_SENT_AT    TIMESTAMP(6) WITH TIME ZONE,
  LAST_SENT_DATE  DATE,
  CREATED_AT      TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
  UPDATED_AT      TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
  CREATED_BY      VARCHAR2(20 CHAR)            NOT NULL,
  UPDATED_BY      VARCHAR2(20 CHAR)            NOT NULL,
  DELETED_AT      TIMESTAMP(6) WITH TIME ZONE,
  CONSTRAINT PK_BS PRIMARY KEY (TEAM_ID, BROADCAST_TYPE)
);

COMMENT ON TABLE BROADCAST_SETTINGS IS '팀별 브로드캐스트 설정. dev DB, TEAMS FK 없음(평문 TEAM_ID). submit-result의 안받음 자동거절 임계값(CONFIG.autoRejectCount, 기본 3)만 사용 — seed 없어도 기본값으로 동작';

COMMIT;
