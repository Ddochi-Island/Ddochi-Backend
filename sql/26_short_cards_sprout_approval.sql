-- ================================================================
-- 26_short_cards_sprout_approval.sql — 짧카 재가 방식 변경 (2026-09-30)
-- ================================================================
-- 짧카 작성은 재가 없이 바로 밭에 올라가고(APPROVAL_STATUS='approved'로 저장),
-- 재가는 3단계(떡잎)로 올라갈 때만 받음: 3단계를 다 채우면 SPROUT_STATUS='pending',
-- 그 짧카가 속한 반의 반장 이상이 재가하면 'approved' → 떡잎.
-- 적용 시점에 떡잎(3단계 완료)인 짧카는 없었음 — 기존 떡잎 인정 처리 불필요.
-- ================================================================

ALTER TABLE SHORT_CARDS ADD (
  SPROUT_STATUS      VARCHAR2(20 CHAR) CHECK (SPROUT_STATUS IN ('pending','approved','rejected')),
  SPROUT_DECIDED_BY  VARCHAR2(50 CHAR),
  SPROUT_DECIDED_AT  TIMESTAMP(6) WITH TIME ZONE
);

-- 재가 대기 중이던 짧카는 전부 밭에 올림(사용자 결정). 반려된 건 그대로.
UPDATE SHORT_CARDS SET APPROVAL_STATUS = 'approved', UPDATED_BY = 'SYSTEM'
 WHERE APPROVAL_STATUS = 'pending' AND DELETED_AT IS NULL;

COMMIT;
