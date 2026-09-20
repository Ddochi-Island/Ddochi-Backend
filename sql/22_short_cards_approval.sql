-- ================================================================
-- 22_short_cards_approval.sql — 짧카 재가(전도팀장/지역장) 컬럼 추가
-- ================================================================

ALTER TABLE SHORT_CARDS ADD APPROVAL_STATUS VARCHAR2(20 CHAR) DEFAULT 'pending' NOT NULL
  CHECK (APPROVAL_STATUS IN ('pending','approved','rejected'));

COMMENT ON COLUMN SHORT_CARDS.APPROVAL_STATUS IS '전도팀장/지역장 재가 여부. 승인돼도 농부일지 폼은 아직 별도 작업';

COMMIT;
