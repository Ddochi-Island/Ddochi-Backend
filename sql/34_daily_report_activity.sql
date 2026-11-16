-- 일일보고 활동자 기준 변경(2026-11-16) — 전단지(flyer)·대체(substitute) 추가, offlineSearch는 옛 데이터용으로 남김
ALTER TABLE DAILY_REPORTS DROP CONSTRAINT SYS_C0025155;
ALTER TABLE DAILY_REPORTS ADD CONSTRAINT CK_DAILY_REPORTS_ACTIVITY CHECK (ACTIVITY IN ('none','online','offline','offlineSearch','flyer','substitute'));
