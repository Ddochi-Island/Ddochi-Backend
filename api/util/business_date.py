# KST 영업일 헬퍼 — services/main/src/util/businessDate.js 포팅.
# 22시(KST) 경계: 22시 이후 활동은 다음 영업일로 집계된다. 일일보고 등에서 씀.
# TIME_ZONE=Asia/Seoul라 datetime.now()가 이미 KST라서 JS판의 +9h 보정은 불필요.
import datetime

BUSINESS_DAY_BOUNDARY_HOUR = 22  # KST


def get_business_date(at=None):
    at = at or datetime.datetime.now()
    if at.hour >= BUSINESS_DAY_BOUNDARY_HOUR:
        at = at + datetime.timedelta(days=1)
    return at.date().isoformat()


def get_dashboard_biz_date(cur_hour, at=None):
    """대시보드 "일일 박제" 스냅샷 날짜 — 22시 정각 스냅샷만 예외적으로 "방금
    끝난 오늘"(자정 기준)로 찍는다. get_business_date()는 22시부터 이미 다음날로
    넘어가버려서, 22시 정각 스냅샷에 그대로 쓰면 "내일" 걸로 잘못 찍히기 때문."""
    at = at or datetime.datetime.now()
    if cur_hour == BUSINESS_DAY_BOUNDARY_HOUR:
        return at.date().isoformat()
    return get_business_date(at)
