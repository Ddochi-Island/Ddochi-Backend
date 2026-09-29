-- ================================================================
-- 24_suggestions.sql — 개발자에게 건의하기(건의함) 저장 테이블
-- ================================================================
-- services/main/src/routes/suggestions.js 포팅. 레거시 SUGGESTIONS는 소스 SQL에
-- 정의가 없어서 라우트가 쓰는 컬럼 그대로 재구성(AUTHOR_SABUN → AUTHOR_MEMBER_ID).
-- 번호(#N)는 텔레그램 알림/건의함 목록 표시용 일련번호.
-- ================================================================

CREATE SEQUENCE SUGGESTIONS_SEQ START WITH 1 INCREMENT BY 1 NOCACHE;

CREATE TABLE SUGGESTIONS (
  SUGGESTION_ID     VARCHAR2(50 CHAR)            PRIMARY KEY,
  SUGGESTION_NUM    NUMBER(10)                   NOT NULL,
  AUTHOR_MEMBER_ID  VARCHAR2(50 CHAR)            NOT NULL,
  AUTHOR_NAME       VARCHAR2(50 CHAR),
  SUBJECT           VARCHAR2(200 CHAR)           NOT NULL,
  CONTENT           CLOB                         NOT NULL,
  CREATED_AT        TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE INDEX IX_SUGGESTIONS_CREATED ON SUGGESTIONS (CREATED_AT DESC);

COMMENT ON TABLE SUGGESTIONS IS '개발자에게 건의하기 — 홈 화면 제출, 관리자 화면 건의함에서 열람';

COMMIT;
