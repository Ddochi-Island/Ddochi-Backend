-- 일일보고 활동자 기준 재변경(2026-11-22) — 대면 B단계(offlineB) 추가. 옛 값(flyer/online/offlineSearch)은 읽을 때 환산
ALTER TABLE DAILY_REPORTS DROP CONSTRAINT CK_DAILY_REPORTS_ACTIVITY;
ALTER TABLE DAILY_REPORTS ADD CONSTRAINT CK_DAILY_REPORTS_ACTIVITY CHECK (ACTIVITY IN ('none','online','offline','offlineSearch','flyer','substitute','offlineB'));
