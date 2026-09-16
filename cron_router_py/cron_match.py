# 5-필드 cron 표현식 매처(KST 기준) — services/cron-router/src/cron/match.js 포팅.
import datetime

_KST = datetime.timezone(datetime.timedelta(hours=9))


def _match_field(field, value, lo_bound, hi_bound):
    if field == '*':
        return True
    for raw_part in field.split(','):
        part = raw_part
        step = 1
        if '/' in part:
            rng, s = part.split('/')
            step = int(s)
            part = rng
        if part == '*':
            lo, hi = lo_bound, hi_bound
        elif '-' in part:
            a, b = part.split('-')
            lo, hi = int(a), int(b)
        else:
            lo = hi = int(part)
        if lo <= value <= hi and (value - lo) % step == 0:
            return True
    return False


def match_cron(expr, at_ms):
    parts = str(expr or '').strip().split()
    if len(parts) != 5:
        return False
    minute, hour, dom, mon, dow = parts
    d = datetime.datetime.fromtimestamp(at_ms / 1000, tz=_KST)
    # Python: Monday=0..Sunday=6, cron dow: Sunday=0..Saturday=6.
    cron_dow = (d.weekday() + 1) % 7
    return (
        _match_field(minute, d.minute, 0, 59)
        and _match_field(hour, d.hour, 0, 23)
        and _match_field(dom, d.day, 1, 31)
        and _match_field(mon, d.month, 1, 12)
        and _match_field(dow, cron_dow, 0, 6)
    )


def find_recent_match(expr, now_ms, last_run_ms, window_ms):
    """lookback window를 1분 단위로 거슬러 올라가며 가장 최근 매칭 분(minute)을 찾음
    (놓친 tick도 window 안이면 따라잡음). 반환값은 매칭된 분의 floor(ms)."""
    minute_ms = 60 * 1000
    # JS Math.ceil(last_run_ms / minute_ms) 와 동일한 올림 나눗셈.
    past_last_min = -(-last_run_ms // minute_ms) * minute_ms if last_run_ms else 0
    start = max(now_ms - window_ms, past_last_min)
    t = now_ms
    while t >= start:
        if match_cron(expr, t):
            return (t // minute_ms) * minute_ms
        t -= minute_ms
    return 0
