# cron_match.py 자체 검증 — Node의 src/cron/match.js와 교차 검증한 값들 고정
from cron_match import find_recent_match, match_cron

NOW = 1789300000000

assert match_cron('0 * * * *', NOW) is False
assert match_cron('*/10 * * * *', NOW) is False
assert find_recent_match('0 * * * *', NOW, 0, 3_600_000) == 1789297200000
assert find_recent_match('0 * * * *', NOW, 1789297200000, 3_600_000) == 1789297200000

# 2026-09-14 09:00 KST(월요일)
MON_0900_KST = 1789344000000
assert match_cron('0 9 * * 1', MON_0900_KST) is True
assert match_cron('0 9 * * 0', MON_0900_KST) is False

print('ok')
