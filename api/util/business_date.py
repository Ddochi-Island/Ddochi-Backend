# KST 영업일 헬퍼 — services/main/src/util/businessDate.js 포팅.
# 22시(KST) 경계: 22시 이후 활동은 다음 영업일로 집계된다. 일일보고 등에서 씀.
# 배포 컨테이너 OS 시간대가 UTC라(TZ 환경변수 미설정) datetime.datetime.now()는
# KST가 아니라 UTC를 돌려줌 — settings.TIME_ZONE='Asia/Seoul'을 실제로 반영하는
# django.utils.timezone 경유로 가져와야 함(2026-09-27 수정, 예전 주석의
# "datetime.now()가 이미 KST" 설명은 틀렸었음).
import datetime

from django.utils import timezone

BUSINESS_DAY_BOUNDARY_HOUR = 22  # KST


def get_business_date(at=None):
    at = at or timezone.localtime()
    if at.hour >= BUSINESS_DAY_BOUNDARY_HOUR:
        at = at + datetime.timedelta(days=1)
    return at.date().isoformat()


def get_dashboard_biz_date(cur_hour, at=None):
    """대시보드 "일일 박제" 스냅샷 날짜 — 22시 정각 스냅샷만 예외적으로 "방금
    끝난 오늘"(자정 기준)로 찍는다. get_business_date()는 22시부터 이미 다음날로
    넘어가버려서, 22시 정각 스냅샷에 그대로 쓰면 "내일" 걸로 잘못 찍히기 때문."""
    at = at or timezone.localtime()
    if cur_hour == BUSINESS_DAY_BOUNDARY_HOUR:
        return at.date().isoformat()
    return get_business_date(at)
