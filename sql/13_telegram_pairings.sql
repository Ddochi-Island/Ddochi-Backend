-- ================================================================
-- 13_telegram_pairings.sql — 텔레그램 채널 /pair 코드 페어링 (신규)
-- ================================================================
-- Ddochi/docs/adr/0012-telegram-pairing-via-slash-command.md 그대로 포팅.
-- 구역(area) 단위 페어링/teamDashboard 특수 케이스는 현재 TelegramConnectModal.vue가
-- 안 써서(팀 단위만) 이번 범위에서 뺌 — 필요해지면 AREA_ID 컬럼 추가.
-- TEAM_ID는 이 프로젝트에 TEAMS 테이블이 없어 MEMBER_AFFILIATION_HISTORIES.REGION_CODE
-- 코드값을 그대로 담는 FK 없는 평문 컬럼(BROADCAST_SETTINGS 등과 동일 패턴).
-- ================================================================

CREATE TABLE TELEGRAM_PAIRINGS (
  CODE             VARCHAR2(16 CHAR)            PRIMARY KEY,
  TEAM_ID          VARCHAR2(20 CHAR)            NOT NULL,
  CHANNEL_TYPE     VARCHAR2(30 CHAR)            NOT NULL,
  ISSUED_BY_SABUN  VARCHAR2(50 CHAR)            NOT NULL,
  ISSUED_AT        TIMESTAMP(6) WITH TIME ZONE  DEFAULT SYSTIMESTAMP NOT NULL,
  EXPIRES_AT       TIMESTAMP(6) WITH TIME ZONE  NOT NULL,
  COMPLETED_AT     TIMESTAMP(6) WITH TIME ZONE,
  CHAT_ID          VARCHAR2(50 CHAR),
  CHAT_TITLE       VARCHAR2(200 CHAR),
  CONSTRAINT FK_TP_ISSUER FOREIGN KEY (ISSUED_BY_SABUN) REFERENCES MEMBERS(MEMBER_ID)
);

-- (team, channel_type)의 미완료(COMPLETED_AT IS NULL) row는 항상 1개만 — "복사" 재클릭은
-- 새 코드 대신 같은 row의 EXPIRES_AT만 갱신하는 방식이라 이 유니크 인덱스로 강제.
CREATE UNIQUE INDEX UQ_TP_ACTIVE ON TELEGRAM_PAIRINGS (
  CASE WHEN COMPLETED_AT IS NULL THEN TEAM_ID || '|' || CHANNEL_TYPE END
);

COMMENT ON TABLE  TELEGRAM_PAIRINGS              IS '텔레그램 채널 연결용 /pair 코드. TTL 10분, 사용 후 COMPLETED_AT 설정되면 재사용 불가';
COMMENT ON COLUMN TELEGRAM_PAIRINGS.CODE         IS '8자 영숫자(혼동 문자 제외) — 어드민이 클립보드로 복사해 텔레그램 방에 /pair CODE로 붙여넣음';
COMMENT ON COLUMN TELEGRAM_PAIRINGS.COMPLETED_AT IS 'NULL=대기중, NOT NULL=봇이 코드를 받아 처리 완료';

COMMIT;
