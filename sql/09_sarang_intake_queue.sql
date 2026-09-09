-- ================================================================
-- 09_sarang_intake_queue.sql — Shed 자동이관(webhook) 대기열 (신규)
-- ================================================================
-- schema-spec.md(Sarang Domain)엔 없는 개념 — shed 프로젝트(별도 저장소)의
-- 신청폼이 Google Apps Script를 거쳐 Ddochi로 리드를 자동 전달할 때, 담당자가
-- "이관받을지/반려할지"를 고르기 전까지 대기시키는 큐. 논의 후 확정:
--
-- SARANG은 "실제로 작업 중인 사랑이"만 담고, 미확인 신청은 이 테이블에 별도로
-- 쌓아둔다. 수락 시에만 SARANG_PERSONAL_INFO/SARANG/SARANG_INFLOW_DETAILS
-- 행을 만들고, 반려 시에는 SARANG 행 자체를 만들지 않는다.
--
-- SOURCE_LINK(유입 링크 1~6): "질적 찾기"(2/4/6팀)와 "선한 양치기"(1/3/5팀)
-- 화면을 가르는 기준이라 대기열에는 필요 — 다만 SARANG 자체에는 안 넣기로
-- 확정(스펙 원칙 유지, 링크 기반 라우팅은 별도 논의 예정).
-- ================================================================

CREATE TABLE SARANG_INTAKE_QUEUE (
  INTAKE_ID             VARCHAR2(50 CHAR)            PRIMARY KEY,
  NAME                  VARCHAR2(50 CHAR)            NOT NULL,
  PHONE                 VARCHAR2(20 CHAR)            NOT NULL,
  PHONE_NORMALIZED      VARCHAR2(20 CHAR)            NOT NULL,
  AGE                   NUMBER(3),
  MBTI                  VARCHAR2(10 CHAR),
  SOURCE_LINK           NUMBER(1)                    NOT NULL CHECK (SOURCE_LINK BETWEEN 1 AND 6),
  REGION_NAME           VARCHAR2(50 CHAR),
  REACTION              VARCHAR2(100 CHAR),
  LOCATION              VARCHAR2(100 CHAR),
  ENV                   VARCHAR2(50 CHAR),
  INTRODUCER_MEMBER_ID  VARCHAR2(50 CHAR),
  HELPER_MEMBER_IDS     VARCHAR2(300 CHAR),
  REST_TYPE             VARCHAR2(50 CHAR),
  TM_RESERVED_AT        TIMESTAMP(6) WITH TIME ZONE,
  STATUS                VARCHAR2(15 CHAR)            DEFAULT 'pending' NOT NULL
                        CHECK (STATUS IN ('pending','submitted','accepted','rejected')),
  REVIEWED_BY_MEMBER_ID VARCHAR2(50 CHAR),
  REVIEWED_AT           TIMESTAMP(6) WITH TIME ZONE,
  CREATED_AT            TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
  CONSTRAINT FK_SIQ_REVIEWER  FOREIGN KEY (REVIEWED_BY_MEMBER_ID) REFERENCES MEMBERS(MEMBER_ID),
  CONSTRAINT CK_SIQ_PHONE_NORM CHECK (REGEXP_LIKE(PHONE_NORMALIZED, '^[0-9]+$'))
);

CREATE INDEX IX_SIQ_PHONE_STATUS ON SARANG_INTAKE_QUEUE (PHONE_NORMALIZED, STATUS);

COMMENT ON TABLE  SARANG_INTAKE_QUEUE             IS 'shed 웹훅 자동이관 대기열 — 수락/반려 전 임시 보관. 수락 시에만 SARANG 계열로 승격';
COMMENT ON COLUMN SARANG_INTAKE_QUEUE.SOURCE_LINK IS '유입 링크 번호(1~6) — 질적 찾기(2/4/6)·선한 양치기(1/3/5) 화면 라우팅 기준. SARANG에는 없음(대기열 전용)';
COMMENT ON COLUMN SARANG_INTAKE_QUEUE.STATUS      IS 'pending=shed 신청 직후, submitted=shed 관리자가 이관하기 클릭(Ddochi 검토 대기), accepted=Ddochi 담당자가 이관받기(SARANG 생성됨), rejected=Ddochi 담당자가 반려(SARANG 생성 안 함)';
COMMENT ON COLUMN SARANG_INTAKE_QUEUE.REST_TYPE   IS '신청 폼에서 고른 휴식 유형 — shed 신청서 자체 필드, SARANG에는 안 넘어감';
COMMENT ON COLUMN SARANG_INTAKE_QUEUE.ENV             IS '환경 — shed 관리자가 "이관하기" 시 채워넣는 값(신청 시점엔 없음)';
COMMENT ON COLUMN SARANG_INTAKE_QUEUE.INTRODUCER_MEMBER_ID IS '유입자의 MEMBERS.MEMBER_ID — shed 관리자가 "이관하기" 시 채워넣음. 이름 텍스트는 안 저장(표시할 땐 MEMBERS 조인). FK 강제 안 함(shed가 이관 응답을 안 보므로 강제 시 조용한 유실 위험)';
COMMENT ON COLUMN SARANG_INTAKE_QUEUE.HELPER_MEMBER_IDS    IS '유입자 추첨에서 낙첨된 조력자들의 MEMBER_ID — 콤마 구분';

COMMIT;
