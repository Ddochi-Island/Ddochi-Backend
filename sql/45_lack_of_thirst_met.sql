-- 갈급부족은 만나 보고 나오는 결과라 항상 ⭕️(탈락)로 저장 — 사유 코드를 DROPOUT 아래에도 둠(2026-11-25). 옛 CANCEL 행은 호환용으로 남김
INSERT INTO MATCH_SUB_REASON_CODES (RESULT_CODE, SUB_CODE, LABEL, SORT_ORDER) VALUES ('DROPOUT', 'LACK_OF_THIRST', '갈급부족', 12);

COMMIT;
