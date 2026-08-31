-- ================================================================
-- 04_prospects.sql — Shed(사쉐) TM 워크보드 핵심 테이블 (dev DB, 축소판)
-- ================================================================
-- 원본: Ddochi/sql/02_prospect.sql (PERSONAL_INFO/PROSPECTS/PROSPECT_HISTORY/
--       PROSPECT_TM_LOGS/PROSPECT_HABJAEYANG 부분만 발췌).
-- 이전 테이블들과 동일한 원칙: SCHEMA_VERSION 제외, REGIONS/TEAMS/AREAS/
-- SHEET_CONFIGS FK 제거(컬럼은 평문으로 유지), 월별 PARTITION 제거(dev 규모).
--
-- PROSPECTS.SNAP_AREA_ID: 체크인된 02_prospect.sql은 NOT NULL(주석상 "트리거
-- 자동 채움")이라 되어있지만, 2026-08-31 prod USER_TAB_COLUMNS 직접 조회 결과
-- 실제로는 NULLABLE — assets.js의 어떤 INSERT/UPDATE 문도 이 컬럼을 채우지
-- 않는다(shed-register 등에서 직접 확인). 트리거 없음, 앱 코드도 안 채움 —
-- 실물 그대로 nullable로 둠.
--
-- PROSPECTS.NUMBER_STATUS/INTRODUCER_NAME/REGISTERED_AT/SHED_RESERVED_AT/
-- TM_NOTE: Ddochi/sql/*.sql에 체크인된 마이그레이션이 없는 컬럼(스키마 드리프트).
-- 위와 동일한 방법으로 prod USER_TAB_COLUMNS를 직접 조회해 타입을 확정.
--
-- SOURCE_TYPE CHECK: 체크인된 DDL은 ('manual','sheet','dolyo','tateam')이지만
-- prod의 실제 CK_P_SOURCE 제약(및 실 데이터)은 'dupcheck'/'online'/'offline'도
-- 허용 — prod 제약을 직접 조회해 그대로 반영.
--
-- PROSPECT_HISTORY.FIELD_KEY/BEFORE_VALUE/AFTER_VALUE/REF_ID,
-- PROSPECT_HABJAEYANG.MBTI/JOB/ATT/DIST/ETC/GWACHEON_MIN/GWACHEON_TRANSFER/
-- CENTER_MIN/CENTER_TRANSFER/SELF_IMAGE/CENTER_ENV/DRUG/MENTAL/FORMAT_VERSION:
-- 체크인된 02_prospect.sql 이후 prod에 추가된 V1-lite 필드(전부 assets.js의
-- submit-result/appendHistoryStmt가 실사용) — 마이그레이션 파일 없음, prod
-- USER_TAB_COLUMNS 직접 조회로 확정.
-- ================================================================

CREATE TABLE PERSONAL_INFO (
  HASH_ID            VARCHAR2(64 CHAR)            PRIMARY KEY,
  NAME               VARCHAR2(50 CHAR)            NOT NULL,
  PHONE              VARCHAR2(20 CHAR)            NOT NULL,
  PHONE_NORMALIZED   VARCHAR2(20 CHAR)            NOT NULL,
  RESIDENCE          VARCHAR2(100 CHAR),
  EXPIRE_AT          TIMESTAMP(6) WITH TIME ZONE,
  CREATED_AT         TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
  UPDATED_AT         TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
  CREATED_BY         VARCHAR2(20 CHAR)            NOT NULL,
  UPDATED_BY         VARCHAR2(20 CHAR)            NOT NULL,
  DELETED_AT         TIMESTAMP(6) WITH TIME ZONE,
  CONSTRAINT CK_PI_PHONE_NORM CHECK (REGEXP_LIKE(PHONE_NORMALIZED, '^[0-9]+$'))
);

CREATE INDEX IX_PI_PHONE_NORM ON PERSONAL_INFO (PHONE_NORMALIZED);

COMMENT ON TABLE  PERSONAL_INFO           IS 'PII 분리(이름/연락처). dev DB, FK 없음, TTL 만료 배치 없음(EXPIRE_AT nullable — 강제 안 함)';
COMMENT ON COLUMN PERSONAL_INFO.HASH_ID   IS 'SHA-256(name+phone) hex. 재신청 시 동일 hash → 이력 자동 연결';

CREATE TABLE PROSPECTS (
  PROSPECT_ID         RAW(16)                      DEFAULT SYS_GUID() PRIMARY KEY,
  PERSONAL_INFO_ID    VARCHAR2(64 CHAR)            NOT NULL,
  TEAM_ID             VARCHAR2(30 CHAR)            NOT NULL,
  MANAGER_SABUN       VARCHAR2(20 CHAR)            NOT NULL,
  GUIDE_SABUN         VARCHAR2(20 CHAR)            NOT NULL,
  TEACHER_SABUN       VARCHAR2(20 CHAR),
  TEACHER_NAME        VARCHAR2(50 CHAR),
  STATUS              VARCHAR2(20 CHAR)            NOT NULL
                      CHECK (STATUS IN (
                        'phoneSearch','approvalPending','meetingFix',
                        'step1','step2','step3Plus',
                        'consultWin','bibleFlow','bibleWin',
                        'gospelReg','centerFix','centerReg','postpone'
                      )),
  IS_DROPPED          NUMBER(1)                    DEFAULT 0 NOT NULL CHECK (IS_DROPPED IN (0,1)),
  DROPPED_REASON      VARCHAR2(500 CHAR),
  APPROVAL_STATUS     VARCHAR2(15 CHAR)
                      CHECK (APPROVAL_STATUS IN ('pending','approved','rejected','auto_rejected')),
  TM_STATUS           VARCHAR2(15 CHAR)
                      CHECK (TM_STATUS IN ('before','active','longTerm','reserved','done')),
  IS_FLAGGED          NUMBER(1)                    DEFAULT 0 NOT NULL CHECK (IS_FLAGGED IN (0,1)),
  BUSINESS_DATE       DATE                         NOT NULL,
  GENDER              VARCHAR2(10 CHAR),
  AGE                 NUMBER(3),
  ON_OFF              VARCHAR2(10 CHAR)            CHECK (ON_OFF IN ('online','offline')),
  PATH                VARCHAR2(100 CHAR),
  STRATEGY_LINK       VARCHAR2(2000 CHAR),
  TOOL                VARCHAR2(100 CHAR),
  SOURCE_TYPE         VARCHAR2(10 CHAR)            NOT NULL
                      CHECK (SOURCE_TYPE IN ('manual','sheet','tateam','dupcheck','dolyo','online','offline')),
  SHEET_CONFIG_ID     VARCHAR2(30 CHAR),
  SNAP_AREA_ID        VARCHAR2(30 CHAR),
  -- Shed 전용(스키마 드리프트, prod 실측 타입 그대로) — assets.js:2205-3071
  NUMBER_STATUS       VARCHAR2(10 CHAR)
                      CHECK (NUMBER_STATUS IN ('pending','pending_dup','confirmed','rejected')),
  INTRODUCER_NAME     VARCHAR2(100 CHAR),
  REGISTERED_AT       TIMESTAMP(6),
  SHED_RESERVED_AT    VARCHAR2(80 CHAR),
  TM_NOTE             CLOB,
  CREATED_AT          TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
  UPDATED_AT          TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
  CREATED_BY          VARCHAR2(20 CHAR)            NOT NULL,
  UPDATED_BY          VARCHAR2(20 CHAR)            NOT NULL,
  DELETED_AT          TIMESTAMP(6) WITH TIME ZONE,
  CONSTRAINT FK_P_PI       FOREIGN KEY (PERSONAL_INFO_ID) REFERENCES PERSONAL_INFO(HASH_ID),
  CONSTRAINT FK_P_MANAGER  FOREIGN KEY (MANAGER_SABUN)    REFERENCES USERS(SABUN),
  CONSTRAINT FK_P_GUIDE    FOREIGN KEY (GUIDE_SABUN)      REFERENCES USERS(SABUN),
  CONSTRAINT FK_P_TEACHER  FOREIGN KEY (TEACHER_SABUN)    REFERENCES USERS(SABUN),
  CONSTRAINT CK_P_DROP_REASON CHECK (
    (IS_DROPPED = 0 AND DROPPED_REASON IS NULL) OR (IS_DROPPED = 1)
  )
);

CREATE INDEX IX_P_TEAM_STATUS_UPD ON PROSPECTS (TEAM_ID, STATUS, UPDATED_AT DESC);
CREATE INDEX IX_P_MANAGER_UPD     ON PROSPECTS (MANAGER_SABUN, UPDATED_AT DESC);
CREATE INDEX IX_P_GUIDE_UPD       ON PROSPECTS (GUIDE_SABUN, UPDATED_AT DESC);
CREATE INDEX IX_P_PI              ON PROSPECTS (PERSONAL_INFO_ID);
CREATE INDEX IX_P_TM_STATUS       ON PROSPECTS (TEAM_ID, TM_STATUS);

COMMENT ON TABLE  PROSPECTS            IS 'Shed 리드 메인 테이블. dev DB, TEAMS/SHEET_CONFIGS FK 없음, 파티션 없음';
COMMENT ON COLUMN PROSPECTS.TEAM_ID    IS 'FK 없는 평문 팀 식별자 (USERS.TEAM_ID와 동일 규칙)';
COMMENT ON COLUMN PROSPECTS.SNAP_AREA_ID IS 'prod 실측 결과 nullable — 트리거/앱코드 어디서도 안 채움';

CREATE TABLE PROSPECT_HISTORY (
  HISTORY_ID         NUMBER(19)                   GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  PROSPECT_ID        RAW(16)                      NOT NULL,
  AUTHOR_SABUN       VARCHAR2(20 CHAR)            NOT NULL,
  CHANGED_BY_SABUN   VARCHAR2(20 CHAR)            NOT NULL,
  DETAIL             CLOB,
  RELATED_LOG_IDS    CLOB,
  BEFORE_HISTORY_ID  NUMBER(19),
  AFTER_HISTORY_ID   NUMBER(19),
  -- 호출 시점 AUTHOR.TEAM_ID/AREA_ID 스냅샷 — 트리거 아님, get_author_context()가 매번 채움
  SNAP_TEAM_ID       VARCHAR2(30 CHAR)            NOT NULL,
  SNAP_AREA_ID       VARCHAR2(30 CHAR)            NOT NULL,
  -- appendHistoryStmt()의 extra 인자(구조화된 되돌리기 정보) — 안 넘기면 전부 NULL
  FIELD_KEY          VARCHAR2(120 CHAR),
  BEFORE_VALUE       CLOB,
  AFTER_VALUE        CLOB,
  REF_ID             VARCHAR2(160 CHAR),
  EVENT_AT           TIMESTAMP(6)                 DEFAULT LOCALTIMESTAMP NOT NULL,
  CONSTRAINT FK_PH_PROSPECT FOREIGN KEY (PROSPECT_ID)      REFERENCES PROSPECTS(PROSPECT_ID) ON DELETE CASCADE,
  CONSTRAINT FK_PH_AUTHOR   FOREIGN KEY (AUTHOR_SABUN)     REFERENCES USERS(SABUN),
  CONSTRAINT FK_PH_CHANGED  FOREIGN KEY (CHANGED_BY_SABUN) REFERENCES USERS(SABUN),
  CONSTRAINT CK_PH_RELATED_JSON CHECK (RELATED_LOG_IDS IS NULL OR RELATED_LOG_IDS IS JSON)
);

CREATE INDEX IX_PH_PROSPECT_TIME ON PROSPECT_HISTORY (PROSPECT_ID, EVENT_AT DESC);

COMMENT ON TABLE PROSPECT_HISTORY IS 'append-only 변경 이력. dev DB, 파티션 없음';

CREATE TABLE PROSPECT_TM_LOGS (
  TM_LOG_ID         NUMBER(19)                   GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  PROSPECT_ID       RAW(16)                      NOT NULL,
  TM_PHASE          VARCHAR2(10 CHAR)            NOT NULL CHECK (TM_PHASE IN (
                      'attempt','progress','report','result'
                    )),
  CATEGORY          VARCHAR2(20 CHAR)            NOT NULL CHECK (CATEGORY IN (
                      'noAnswer','tmReserved','meetingFix','longTerm','bihap','rejected'
                    )),
  CONTENT           CLOB,
  AUTHOR_SABUN      VARCHAR2(20 CHAR)            NOT NULL,
  BEFORE_TM_LOG_ID  NUMBER(19),
  AFTER_TM_LOG_ID   NUMBER(19),
  SNAP_TEAM_ID      VARCHAR2(30 CHAR)            NOT NULL,
  SNAP_AREA_ID      VARCHAR2(30 CHAR)            NOT NULL,
  EVENT_AT          TIMESTAMP(6)                 DEFAULT LOCALTIMESTAMP NOT NULL,
  CONSTRAINT FK_PTL_PROSPECT FOREIGN KEY (PROSPECT_ID)  REFERENCES PROSPECTS(PROSPECT_ID) ON DELETE CASCADE,
  CONSTRAINT FK_PTL_AUTHOR   FOREIGN KEY (AUTHOR_SABUN) REFERENCES USERS(SABUN)
);

CREATE INDEX IX_PTL_PROSPECT_TIME ON PROSPECT_TM_LOGS (PROSPECT_ID, EVENT_AT DESC);

COMMENT ON TABLE PROSPECT_TM_LOGS IS 'TM 행위 로그, append-only. dev DB, 파티션 없음';

CREATE TABLE PROSPECT_HABJAEYANG (
  HABJAEYANG_ID    NUMBER(19)                   GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  PROSPECT_ID      RAW(16)                      NOT NULL,
  REPLIED          NUMBER(1)                    DEFAULT 0 NOT NULL CHECK (REPLIED IN (0,1)),
  WINDOW_OPENED    NUMBER(1)                    DEFAULT 0 NOT NULL CHECK (WINDOW_OPENED IN (0,1)),
  PURPOSE          VARCHAR2(1000 CHAR),
  QNA              CLOB,
  PLAN_TEXT        CLOB,
  SCHEDULE_TEXT    CLOB,
  TROUBLE          VARCHAR2(1000 CHAR),
  WARY             VARCHAR2(1000 CHAR),
  TM_USER_SABUN    VARCHAR2(20 CHAR),
  HJ_MSG_ID        NUMBER(19),
  HJ_CHAT_ID       VARCHAR2(30 CHAR),
  HJ_SENT_AT       TIMESTAMP(6) WITH TIME ZONE,
  -- V1-lite 필드 (FORMAT_VERSION=2 갱신 시 submit-result가 채움) — prod 실측
  MBTI             VARCHAR2(10 CHAR),
  JOB              VARCHAR2(500 CHAR),
  ATT              VARCHAR2(500 CHAR),
  DIST             VARCHAR2(500 CHAR),
  ETC              VARCHAR2(2000 CHAR),
  GWACHEON_MIN     NUMBER,
  GWACHEON_TRANSFER NUMBER,
  CENTER_MIN       NUMBER,
  CENTER_TRANSFER  NUMBER,
  SELF_IMAGE       VARCHAR2(12000 CHAR),
  CENTER_ENV       CHAR(1)                      CHECK (CENTER_ENV IN ('O','X')),
  DRUG             CHAR(1)                      CHECK (DRUG IN ('O','X')),
  MENTAL           CHAR(1)                      CHECK (MENTAL IN ('O','X')),
  FORMAT_VERSION   NUMBER                       DEFAULT 1,
  ACTIVE           NUMBER(1)                    DEFAULT 1 NOT NULL CHECK (ACTIVE IN (0,1)),
  CREATED_AT       TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
  UPDATED_AT       TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
  CREATED_BY       VARCHAR2(20 CHAR)            NOT NULL,
  UPDATED_BY       VARCHAR2(20 CHAR)            NOT NULL,
  DELETED_AT       TIMESTAMP(6) WITH TIME ZONE,
  CONSTRAINT FK_HJ_PROSPECT FOREIGN KEY (PROSPECT_ID)   REFERENCES PROSPECTS(PROSPECT_ID) ON DELETE CASCADE,
  CONSTRAINT FK_HJ_TM       FOREIGN KEY (TM_USER_SABUN) REFERENCES USERS(SABUN)
);

CREATE INDEX IX_HJ_PROSPECT ON PROSPECT_HABJAEYANG (PROSPECT_ID, CREATED_AT DESC);
CREATE INDEX IX_HJ_TM       ON PROSPECT_HABJAEYANG (TM_USER_SABUN, CREATED_AT DESC);

COMMENT ON TABLE PROSPECT_HABJAEYANG IS '합재양(매칭/상담/재가 후). PROSPECTS:HJ = 1:N(보통 1:1), ACTIVE=1인 행이 활성본';

COMMIT;
