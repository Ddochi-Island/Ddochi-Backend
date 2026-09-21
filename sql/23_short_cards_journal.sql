-- ================================================================
-- 23_short_cards_journal.sql — 농부일지(짧카 3단계 성장 기록) 컬럼 추가
-- ================================================================
-- 씨앗(1단계)/새싹(2단계)/떡잎(3단계) 판정은 이 컬럼들의 채움 여부로 계산
-- (api/views/short_card.py의 _journal_stage). 이름/성별/나이/연락처/거주지/
-- 학교전공/1년환경은 이미 짧카 필드에 있어서 재사용, 새로 필요한 것만 추가.

ALTER TABLE SHORT_CARDS ADD (
  FAITH_STATUS       VARCHAR2(10 CHAR)  CHECK (FAITH_STATUS IN ('무','휴','신앙')),
  RELATION           VARCHAR2(200 CHAR),
  PERSONALITY        VARCHAR2(500 CHAR),
  HOBBY              VARCHAR2(500 CHAR),
  HAS_PARTNER        VARCHAR2(20 CHAR),
  FAMILY_RELATION    VARCHAR2(500 CHAR),
  DESIRED_IMAGE      VARCHAR2(500 CHAR),
  RECENT_CONCERN     VARCHAR2(500 CHAR),
  FAMILY_ATMOSPHERE  VARCHAR2(500 CHAR),
  HUMAN_RELATIONS    VARCHAR2(500 CHAR),
  NOTE_SPECIAL       VARCHAR2(1000 CHAR),
  GUIDE_COMMENT      VARCHAR2(500 CHAR)
);

COMMENT ON COLUMN SHORT_CARDS.FAITH_STATUS IS '농부일지 신앙여부: 무/휴/신앙';
COMMENT ON COLUMN SHORT_CARDS.RELATION IS '농부일지 1단계(씨앗): 관계';
COMMENT ON COLUMN SHORT_CARDS.PERSONALITY IS '농부일지 2단계(새싹): 성격';
COMMENT ON COLUMN SHORT_CARDS.DESIRED_IMAGE IS '농부일지 3단계(떡잎): 되고싶은 모습';

COMMIT;
