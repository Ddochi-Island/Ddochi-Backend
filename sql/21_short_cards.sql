-- ================================================================
-- 21_short_cards.sql — 짧카(지역원 개인 지인 기록) 테이블
-- ================================================================
-- 짧카는 SARANG 아웃리치 파이프라인과 무관 — 지역원이 이미 알고 있는 개인
-- 지인을 기록하는 최소 정보 카드. SARANG_PERSONAL_INFO 같은 별도 PII 테이블
-- 분리 없음(사랑이처럼 여러 출처 간 전화번호 중복 제거가 필요 없어서).
-- ================================================================

CREATE TABLE SHORT_CARDS (
  SHORT_CARD_ID     VARCHAR2(32 CHAR)            PRIMARY KEY,
  MEMBER_ID         VARCHAR2(50 CHAR)            NOT NULL,
  NAME              VARCHAR2(100 CHAR)           NOT NULL,
  AGE               NUMBER(3),
  GENDER            VARCHAR2(10 CHAR)            CHECK (GENDER IN ('남','여')),
  PHONE             VARCHAR2(30 CHAR),
  PHONE_NORMALIZED  VARCHAR2(20 CHAR),
  SCHOOL_MAJOR      VARCHAR2(200 CHAR),
  ENVIRONMENT       VARCHAR2(1000 CHAR),
  RESIDENCE         VARCHAR2(200 CHAR),
  RELIGION          VARCHAR2(20 CHAR)            CHECK (RELIGION IN ('무교','기독교','불교','천주교','기타')),
  RECRUIT_NOTE      VARCHAR2(1000 CHAR),
  CREATED_AT        TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
  UPDATED_AT        TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
  CREATED_BY        VARCHAR2(50 CHAR)            NOT NULL,
  UPDATED_BY        VARCHAR2(50 CHAR)            NOT NULL,
  DELETED_AT        TIMESTAMP(6) WITH TIME ZONE,
  CONSTRAINT FK_SC_MEMBER FOREIGN KEY (MEMBER_ID) REFERENCES MEMBERS(MEMBER_ID)
);

CREATE INDEX IX_SC_MEMBER ON SHORT_CARDS (MEMBER_ID);
CREATE INDEX IX_SC_PHONE ON SHORT_CARDS (PHONE_NORMALIZED);

COMMENT ON TABLE  SHORT_CARDS               IS '짧카 — 지역원 개인 지인 기록(농부일지용 밭 시드). SARANG 아웃리치 파이프라인과 무관';
COMMENT ON COLUMN SHORT_CARDS.MEMBER_ID     IS '작성자(인도자) — 제출한 지역원의 사번';
COMMENT ON COLUMN SHORT_CARDS.PHONE_NORMALIZED IS '숫자만 남긴 번호 — 지역원 간 중복 짧카 감지용';
COMMENT ON COLUMN SHORT_CARDS.RECRUIT_NOTE  IS '따기요소/고민';

COMMIT;
