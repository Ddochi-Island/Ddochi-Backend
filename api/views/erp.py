# ERP(관리자 분석) API — 구 erp.ddochi.cloud(Node, 구 PROSPECTS 스키마)를 V2 SARANG 기준으로 옮긴 것.
# 섭외이력 조회 · TM 결과 집계 · 전환 퍼널 · 주간 보고서. 기준/용어 매핑은 erp-v2/context-notes.md.
# 집계는 (지역, 구역) 단위 행으로 내려주고, 지역/구역 드릴다운·합계는 프론트에서 묶음.
import datetime

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from api.auth.gate import require_jwt
from api.clients.data_router import DataRouterClient
from api.views.daily_report import _json_body

# 사랑이 지역 = 유입자(없으면 이관받은 사람)의 현재 소속 — 다른 화면과 같은 규칙
_INTRO_MAH = """JOIN MEMBER_AFFILIATION_HISTORIES mah
               ON mah.MEMBER_ID = COALESCE((SELECT x.INTRODUCER_MEMBER_ID FROM SARANG_INFLOW_DETAILS x WHERE x.SARANG_ID = s.SARANG_ID), s.INFLOW_MEMBER_ID)
              AND mah.IS_CURRENT = 1"""
# 매칭 결과는 인도자(활성 합재양 GUIDE) 기준 — 매칭 현황판과 같은 규칙
_GUIDE_MAH = """JOIN MEMBER_AFFILIATION_HISTORIES mah
               ON mah.MEMBER_ID = COALESCE((SELECT g.GUIDE_MEMBER_ID FROM SARANG_HAB_JAE_YANG g WHERE g.SARANG_ID = s.SARANG_ID AND g.IS_ACTIVE = 1 AND ROWNUM = 1),
                                           (SELECT x.INTRODUCER_MEMBER_ID FROM SARANG_INFLOW_DETAILS x WHERE x.SARANG_ID = s.SARANG_ID), s.INFLOW_MEMBER_ID)
              AND mah.IS_CURRENT = 1"""
# 실제로 교사와 만난 매칭 결과(취소/밀림/미기입은 안 만난 것)
_MET_RESULTS = "('UNFIT', 'DROPOUT', 'SECOND_MEET', 'CONSULT_WIN')"
_STAGES_FROM = {  # 그 단계 이상(드랍돼도 STAGE는 그대로 남음)
    '만픽': "('만픽','합재양','재가','매칭','상따','성홀','성따','복방','센')",
    '합재양': "('합재양','재가','매칭','상따','성홀','성따','복방','센')",
    '재가': "('재가','매칭','상따','성홀','성따','복방','센')",
    '상따': "('상따','성홀','성따','복방','센')",
}


def _in_range(col):
    """KST 달력 날짜 [from, to] — 바인드 2개(from, to 문자열 'YYYY-MM-DD')를 차례로 받음."""
    return (f"{col} >= FROM_TZ(TO_TIMESTAMP(?, 'YYYY-MM-DD'), 'Asia/Seoul') "
            f"AND {col} < FROM_TZ(TO_TIMESTAMP(?, 'YYYY-MM-DD'), 'Asia/Seoul') + INTERVAL '1' DAY")


def _numbered(sql):
    """? 자리표시를 :1, :2 … 로 — data_router는 같은 번호를 두 번 못 씀(ORA-01008)이라 매번 새 번호."""
    out, n = [], 0
    for ch in sql:
        if ch == '?':
            n += 1
            out.append(f':{n}')
        else:
            out.append(ch)
    return ''.join(out)


def _q(client, sql, args, **opts):
    return client.query(_numbered(sql), args, **opts)


def _is_admin(request, client):
    # suggestions_list와 같은 게이트 — 홈 ERP 버튼 비번(adminUnlocked) 또는 관리자급(SCOPE='global') 직책
    return request.user.get('adminUnlocked') or client.query_one(
        """SELECT 1 AS OK FROM MEMBER_POSITION_MAPPINGS mpm
             JOIN POSITION_CODES pc ON pc.POSITION_CODE = mpm.POSITION_CODE
            WHERE mpm.MEMBER_ID = :1 AND pc.SCOPE = 'global'""",
        [request.user['sabun']],
    )


def _admin_view(fn):
    """POST + JWT + 관리자 확인 후 fn(client, body) 결과를 JSON으로."""
    @csrf_exempt
    @require_jwt
    def view(request, *args, **kwargs):
        if request.method != 'POST':
            return JsonResponse({'error': 'method_not_allowed'}, status=405)
        client = DataRouterClient()
        if not _is_admin(request, client):
            return JsonResponse({'success': False, 'message': '관리자만 볼 수 있어'}, status=403)
        body = _json_body(request)
        try:
            return JsonResponse({'success': True, **fn(client, body)})
        except ValueError as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)
    view.__name__ = fn.__name__
    return view


def _dates(body):
    try:
        frm = datetime.date.fromisoformat(str(body.get('from') or ''))
        to = datetime.date.fromisoformat(str(body.get('to') or ''))
    except ValueError:
        raise ValueError('기간(from/to)을 YYYY-MM-DD로 보내줘')
    if to < frm or (to - frm).days > 400:
        raise ValueError('기간이 이상해 (시작 ≤ 끝, 최대 400일)')
    return frm, to


# ── 섭외이력 조회 ──────────────────────────────────────────────

@_admin_view
def erp_search(client, body):
    q = str(body.get('q') or '').strip()
    if not q:
        raise ValueError('이름이나 전화번호를 넣어줘')
    digits = ''.join(ch for ch in q if ch.isdigit())
    cond, arg = ('spi.PHONE_NORMALIZED LIKE ?', f'%{digits}%') if len(digits) >= 4 else ('spi.NAME LIKE ?', f'%{q}%')
    rows = _q(client, f"""
        SELECT s.SARANG_ID, spi.NAME, spi.PHONE, s.STAGE, s.INFLOW_DATE, mah.REGION_CODE, mah.DISTRICT_CODE,
               COALESCE(im.NAME, m.NAME) AS INTRODUCER_NAME, gm.NAME AS GUIDE_NAME
          FROM SARANG s
          JOIN SARANG_PERSONAL_INFO spi ON spi.PERSONAL_INFO_ID = s.PERSONAL_INFO_ID
          JOIN MEMBERS m ON m.MEMBER_ID = s.INFLOW_MEMBER_ID
          {_INTRO_MAH}
          LEFT JOIN SARANG_INFLOW_DETAILS sid ON sid.SARANG_ID = s.SARANG_ID
          LEFT JOIN MEMBERS im ON im.MEMBER_ID = sid.INTRODUCER_MEMBER_ID
          LEFT JOIN SARANG_HAB_JAE_YANG h ON h.SARANG_ID = s.SARANG_ID AND h.IS_ACTIVE = 1
          LEFT JOIN MEMBERS gm ON gm.MEMBER_ID = h.GUIDE_MEMBER_ID
         WHERE s.DELETED_AT IS NULL AND {cond}
         ORDER BY s.INFLOW_DATE DESC""", [arg], fetch_limit=100)
    return {'list': rows}


def _match_label(r):
    """"N차 만남 · 결과" — 2차만남(SECOND_MEET) 결과는 다음 만남을 잡았다는 뜻이라 "N+1차 만남 잡음"으로."""
    deg = int(r['match_degree'] or 1)
    attempt = int(r['attempt_count'] or 1)
    head = f"{deg}차 만남" + (f" ({attempt}번째 일정)" if attempt > 1 else '')
    result = f"{deg + 1}차 만남 잡음" if r['result_label'] == '2차만남' else r['result_label']
    return f"{head} · {result}"


@_admin_view
def erp_sarang_detail(client, body):
    sid = str(body.get('sarangId') or '')
    info = client.query_one(
        f"""SELECT s.SARANG_ID, spi.NAME, spi.PHONE, spi.RESIDENCE_STATION, s.AGE, s.GENDER, s.MBTI, s.STAGE,
                   s.CURRENT_PROCESS, s.RECRUITMENT_TYPE, s.INFLOW_DATE, mah.REGION_CODE, mah.DISTRICT_CODE,
                   COALESCE(im.NAME, m.NAME) AS INTRODUCER_NAME, sid.REACTION, sid.LOCATION, sid.ENV, sid.SOURCE_LINK,
                   h.ROUTE, h.TOOL, h.APPROVAL_STATUS, h.MATCH_SCHEDULED_AT,
                   gm.NAME AS GUIDE_NAME, cm.NAME AS CALLER_NAME, COALESCE(tm.NAME, h.TEACHER_NAME_OVERRIDE) AS TEACHER_NAME
              FROM SARANG s
              JOIN SARANG_PERSONAL_INFO spi ON spi.PERSONAL_INFO_ID = s.PERSONAL_INFO_ID
              JOIN MEMBERS m ON m.MEMBER_ID = s.INFLOW_MEMBER_ID
              {_INTRO_MAH}
              LEFT JOIN SARANG_INFLOW_DETAILS sid ON sid.SARANG_ID = s.SARANG_ID
              LEFT JOIN MEMBERS im ON im.MEMBER_ID = sid.INTRODUCER_MEMBER_ID
              LEFT JOIN SARANG_HAB_JAE_YANG h ON h.SARANG_ID = s.SARANG_ID AND h.IS_ACTIVE = 1
              LEFT JOIN MEMBERS gm ON gm.MEMBER_ID = h.GUIDE_MEMBER_ID
              LEFT JOIN MEMBERS cm ON cm.MEMBER_ID = h.CALLER_MEMBER_ID
              LEFT JOIN MEMBERS tm ON tm.MEMBER_ID = h.TEACHER_MEMBER_ID
             WHERE s.SARANG_ID = :1 AND s.DELETED_AT IS NULL""", [sid])
    if not info:
        raise ValueError('없는 사랑이야')
    calls = client.query(
        """SELECT tl.CREATED_AT AS AT, trc.LABEL, COALESCE(tsr.LABEL, tl.SUB_REASON) AS DETAIL, m.NAME AS ACTOR
             FROM TM_LOGS tl JOIN TM_RESULT_CODES trc ON trc.RESULT_CODE = tl.RESULT
             LEFT JOIN TM_SUB_REASON_CODES tsr ON tsr.RESULT_CODE = tl.RESULT AND tsr.SUB_CODE = tl.SUB_REASON
             JOIN MEMBERS m ON m.MEMBER_ID = tl.CALLER_MEMBER_ID
            WHERE tl.SARANG_ID = :1""", [sid])
    acts = client.query(
        """SELECT al.CREATED_AT AS AT, al.EVENT_TYPE AS LABEL, m.NAME AS ACTOR
             FROM SARANG_ACTIVITY_LOGS al JOIN MEMBERS m ON m.MEMBER_ID = al.ACTOR_MEMBER_ID
            WHERE al.SARANG_ID = :1""", [sid])
    # 매칭 이력엔 교사가 안 채워짐(교사는 합재양에만 저장) → 활성 합재양 교사로 보충. 세부사유는 코드 → 라벨
    matches = client.query(
        """SELECT COALESCE(mh.MATCHED_AT, mh.CREATED_AT) AS AT, mh.MATCH_DEGREE, mh.ATTEMPT_COUNT,
                  COALESCE(mrc.LABEL, '진행 예정') AS RESULT_LABEL, COALESCE(msr.LABEL, mh.SUB_REASON) AS SUB_REASON, mh.MATCH_LOCATION,
                  COALESCE(m.NAME, h.TEACHER_NAME_OVERRIDE) AS TEACHER
             FROM SARANG_MATCH_HISTORIES mh
             LEFT JOIN MATCH_RESULT_CODES mrc ON mrc.RESULT_CODE = mh.RESULT
             LEFT JOIN MATCH_SUB_REASON_CODES msr ON msr.RESULT_CODE = mh.RESULT AND msr.SUB_CODE = mh.SUB_REASON
             LEFT JOIN SARANG_HAB_JAE_YANG h ON h.SARANG_ID = mh.SARANG_ID AND h.IS_ACTIVE = 1
             LEFT JOIN MEMBERS m ON m.MEMBER_ID = COALESCE(mh.TEACHER_MEMBER_ID, h.TEACHER_MEMBER_ID)
            WHERE mh.SARANG_ID = :1""", [sid])
    timeline = (
        [{'at': info['inflow_date'], 'kind': 'inflow', 'label': '찾기', 'actor': info['introducer_name']}]
        + [{'at': r['at'], 'kind': 'call', 'label': r['label'], 'detail': r['detail'], 'actor': r['actor']} for r in calls]
        + [{'at': r['at'], 'kind': 'activity', 'label': r['label'], 'actor': r['actor']} for r in acts]
        + [{'at': r['at'], 'kind': 'match', 'label': _match_label(r),
            'detail': ' / '.join(x for x in (r['sub_reason'], r['match_location']) if x), 'actor': r['teacher']}
           for r in matches]
    )
    timeline.sort(key=lambda x: x['at'] or '', reverse=True)
    return {'info': info, 'timeline': timeline}


# ── TM 결과 집계 ──────────────────────────────────────────────

@_admin_view
def erp_tm_stats(client, body):
    """통화한 사람(현재 소속)별 결과 건수 + 재가(그 사랑이의 마지막 만남픽스를 잡은 사람에게 귀속)."""
    frm, to = _dates(body)
    calls = _q(client, f"""
        SELECT tl.CALLER_MEMBER_ID AS MEMBER_ID, m.NAME, mah.REGION_CODE, mah.DISTRICT_CODE, tl.RESULT, COUNT(*) AS N
          FROM TM_LOGS tl
          JOIN MEMBERS m ON m.MEMBER_ID = tl.CALLER_MEMBER_ID
          LEFT JOIN MEMBER_AFFILIATION_HISTORIES mah ON mah.MEMBER_ID = tl.CALLER_MEMBER_ID AND mah.IS_CURRENT = 1
         WHERE {_in_range('tl.CREATED_AT')}
         GROUP BY tl.CALLER_MEMBER_ID, m.NAME, mah.REGION_CODE, mah.DISTRICT_CODE, tl.RESULT""",
        [frm.isoformat(), to.isoformat()], fetch_limit=20000)
    jaega = _q(client, f"""
        SELECT mf.CALLER_MEMBER_ID AS MEMBER_ID, m.NAME, mah.REGION_CODE, mah.DISTRICT_CODE, COUNT(DISTINCT al.SARANG_ID) AS N
          FROM SARANG_ACTIVITY_LOGS al
          JOIN (SELECT SARANG_ID, MAX(CALLER_MEMBER_ID) KEEP (DENSE_RANK LAST ORDER BY CREATED_AT) AS CALLER_MEMBER_ID
                  FROM TM_LOGS WHERE RESULT = 'MEET_FIX' GROUP BY SARANG_ID) mf ON mf.SARANG_ID = al.SARANG_ID
          JOIN MEMBERS m ON m.MEMBER_ID = mf.CALLER_MEMBER_ID
          LEFT JOIN MEMBER_AFFILIATION_HISTORIES mah ON mah.MEMBER_ID = mf.CALLER_MEMBER_ID AND mah.IS_CURRENT = 1
         WHERE al.EVENT_TYPE = '재가처리' AND {_in_range('al.CREATED_AT')}
         GROUP BY mf.CALLER_MEMBER_ID, m.NAME, mah.REGION_CODE, mah.DISTRICT_CODE""",
        [frm.isoformat(), to.isoformat()], fetch_limit=5000)

    people = {}

    def person(r):
        return people.setdefault(r['member_id'], {
            'memberId': r['member_id'], 'name': r['name'], 'region': r['region_code'], 'district': r['district_code'],
            'total': 0, 'NO_ANSWER': 0, 'RESERVED_TM': 0, 'MEET_FIX': 0, 'UNFIT': 0, 'REJECT': 0, 'INVALID': 0, 'jaega': 0,
        })
    for r in calls:
        p = person(r)
        p[r['result']] = p.get(r['result'], 0) + int(r['n'])
        p['total'] += int(r['n'])
    for r in jaega:
        person(r)['jaega'] += int(r['n'])
    return {'rows': list(people.values())}


# ── 기간 지표 (주간 보고서 · 퍼널 기간 내 발생) ───────────────────

def _period_metrics(client, frm, to, extended=False):
    """(지역, 구역)별 기간 내 발생 건수. 사랑이 단위 지표는 사람당 한 번만 셈.
    extended=True(주간 보고서)면 TM 활동·이관 대기열 지표도 같이."""
    a = [frm.isoformat(), to.isoformat()]
    out = {}

    def add(rows, key=None):
        for r in rows:
            k = (r['region_code'], r['district_code'])
            m = out.setdefault(k, {})
            name = key or r['k']
            m[name] = m.get(name, 0) + int(r['n'] or 0)

    add(_q(client, f"""
        SELECT mah.REGION_CODE, mah.DISTRICT_CODE, CASE s.RECRUITMENT_TYPE WHEN 'ONLINE' THEN 'inflowOn' ELSE 'inflowOff' END AS K, COUNT(*) AS N
          FROM SARANG s {_INTRO_MAH}
         WHERE s.DELETED_AT IS NULL AND {_in_range('s.INFLOW_DATE')}
         GROUP BY mah.REGION_CODE, mah.DISTRICT_CODE, s.RECRUITMENT_TYPE""", a))
    # 만남픽스 — 티엠 '만남 픽스' 기록. 합재양에서 바로 등록돼 티엠 기록이 아예 없는 건은 합재양 작성 시점을 만남픽스로 봄
    add(_q(client, f"""
        SELECT mah.REGION_CODE, mah.DISTRICT_CODE, COUNT(DISTINCT s.SARANG_ID) AS N
          FROM (SELECT SARANG_ID FROM TM_LOGS tl WHERE tl.RESULT = 'MEET_FIX' AND {_in_range('tl.CREATED_AT')}
                UNION
                SELECT al.SARANG_ID FROM SARANG_ACTIVITY_LOGS al
                 WHERE al.EVENT_TYPE = '합재양작성' AND {_in_range('al.CREATED_AT')}
                   AND NOT EXISTS (SELECT 1 FROM TM_LOGS t WHERE t.SARANG_ID = al.SARANG_ID AND t.RESULT = 'MEET_FIX')) e
          JOIN SARANG s ON s.SARANG_ID = e.SARANG_ID AND s.DELETED_AT IS NULL {_INTRO_MAH}
         GROUP BY mah.REGION_CODE, mah.DISTRICT_CODE""", a + a), 'meetFix')
    for event, key in (('합재양작성', 'hjy'), ('재가처리', 'jaega')):
        add(_q(client, f"""
            SELECT mah.REGION_CODE, mah.DISTRICT_CODE, COUNT(DISTINCT s.SARANG_ID) AS N
              FROM SARANG_ACTIVITY_LOGS al JOIN SARANG s ON s.SARANG_ID = al.SARANG_ID AND s.DELETED_AT IS NULL {_INTRO_MAH}
             WHERE al.EVENT_TYPE = ? AND {_in_range('al.CREATED_AT')}
             GROUP BY mah.REGION_CODE, mah.DISTRICT_CODE""", [event, *a]), key)
    # 매칭 결과 — 만남 예정일 기준, 결과 미기입은 PENDING(진행 예정)
    add(_q(client, f"""
        SELECT mah.REGION_CODE, mah.DISTRICT_CODE, 'match_' || NVL(mh.RESULT, 'PENDING') AS K, COUNT(*) AS N
          FROM SARANG_MATCH_HISTORIES mh JOIN SARANG s ON s.SARANG_ID = mh.SARANG_ID AND s.DELETED_AT IS NULL {_GUIDE_MAH}
         WHERE {_in_range('mh.MATCHED_AT')}
         GROUP BY mah.REGION_CODE, mah.DISTRICT_CODE, mh.RESULT""", a))
    add(_q(client, f"""
        SELECT mah.REGION_CODE, mah.DISTRICT_CODE, COUNT(DISTINCT s.SARANG_ID) AS N
          FROM SARANG_MATCH_HISTORIES mh JOIN SARANG s ON s.SARANG_ID = mh.SARANG_ID AND s.DELETED_AT IS NULL {_GUIDE_MAH}
         WHERE mh.RESULT IN {_MET_RESULTS} AND {_in_range('mh.MATCHED_AT')}
         GROUP BY mah.REGION_CODE, mah.DISTRICT_CODE""", a), 'met')
    # 일일보고 — 제출 시점 소속 스냅샷, REPORT_DATE는 이미 영업일(22시 롤오버)
    for r in client.query(
        """SELECT SNAP_REGION_CODE AS REGION_CODE, SNAP_DISTRICT_CODE AS DISTRICT_CODE,
                  SUM(TALK_COUNT) AS TALK, SUM(DM_COUNT) AS DM, SUM(QR_COUNT) AS QR, SUM(ONLINE_INTAKE_COUNT) AS ONLINE_INTAKE,
                  COUNT(*) AS REPORTS
             FROM DAILY_REPORTS
            WHERE DELETED_AT IS NULL AND REPORT_DATE BETWEEN TO_DATE(:1, 'YYYY-MM-DD') AND TO_DATE(:2, 'YYYY-MM-DD')
            GROUP BY SNAP_REGION_CODE, SNAP_DISTRICT_CODE""", a):
        m = out.setdefault((r['region_code'], r['district_code']), {})
        for k in ('talk', 'dm', 'qr', 'online_intake', 'reports'):
            m[k] = m.get(k, 0) + int(r[k] or 0)

    if extended:
        _tm_and_queue_metrics(client, a, add)

    return [{'region': k[0], 'district': k[1], **v} for k, v in out.items()]


def _tm_and_queue_metrics(client, a, add):
    # TM 활동 — 통화한 사람(현재 소속) 기준. 결과별 건수 + 티엠 돌린 사람 수 + 통화한 사랑이 수
    add(_q(client, f"""
        SELECT mah.REGION_CODE, mah.DISTRICT_CODE, 'tm_' || tl.RESULT AS K, COUNT(*) AS N
          FROM TM_LOGS tl JOIN MEMBER_AFFILIATION_HISTORIES mah ON mah.MEMBER_ID = tl.CALLER_MEMBER_ID AND mah.IS_CURRENT = 1
         WHERE {_in_range('tl.CREATED_AT')}
         GROUP BY mah.REGION_CODE, mah.DISTRICT_CODE, tl.RESULT""", a))
    for key, expr in (('tm_callers', 'tl.CALLER_MEMBER_ID'), ('tm_people', 'tl.SARANG_ID')):
        add(_q(client, f"""
            SELECT mah.REGION_CODE, mah.DISTRICT_CODE, COUNT(DISTINCT {expr}) AS N
              FROM TM_LOGS tl JOIN MEMBER_AFFILIATION_HISTORIES mah ON mah.MEMBER_ID = tl.CALLER_MEMBER_ID AND mah.IS_CURRENT = 1
             WHERE {_in_range('tl.CREATED_AT')}
             GROUP BY mah.REGION_CODE, mah.DISTRICT_CODE""", a), key)
    # 이관받고 첫 통화까지 — 기간 안에 이관받은 사람 기준(유입자 지역). 평균은 프론트에서 합/건수로
    for r in _q(client, f"""
        SELECT mah.REGION_CODE, mah.DISTRICT_CODE, COUNT(*) AS N,
               SUM((CAST(f.FIRST_AT AS DATE) - CAST(s.CREATED_AT AS DATE)) * 24) AS HOURS
          FROM SARANG s
          JOIN SARANG_INFLOW_DETAILS sid ON sid.SARANG_ID = s.SARANG_ID
          JOIN MEMBER_AFFILIATION_HISTORIES mah ON mah.MEMBER_ID = COALESCE(sid.INTRODUCER_MEMBER_ID, s.INFLOW_MEMBER_ID) AND mah.IS_CURRENT = 1
          JOIN (SELECT SARANG_ID, MIN(CREATED_AT) AS FIRST_AT FROM TM_LOGS GROUP BY SARANG_ID) f ON f.SARANG_ID = s.SARANG_ID
         WHERE s.DELETED_AT IS NULL AND {_in_range('s.CREATED_AT')}
         GROUP BY mah.REGION_CODE, mah.DISTRICT_CODE""", a):
        add([{**r, 'k': 'ft_n'}])
        add([{**r, 'k': 'ft_hours', 'n': round(float(r['hours'] or 0))}])
    # 이관 대기열 — 유입자 지역(없으면 shed 링크 번호). 신청 = shed 신청 시각, 이관·반려 = 처리 시각
    q_mah = """LEFT JOIN MEMBER_AFFILIATION_HISTORIES mah ON mah.MEMBER_ID = q.INTRODUCER_MEMBER_ID AND mah.IS_CURRENT = 1"""
    add(_q(client, f"""
        SELECT COALESCE(mah.REGION_CODE, TO_CHAR(q.SOURCE_LINK)) AS REGION_CODE, mah.DISTRICT_CODE, COUNT(*) AS N
          FROM SARANG_INTAKE_QUEUE q {q_mah}
         WHERE {_in_range('COALESCE(q.APPLIED_AT, q.CREATED_AT)')}
         GROUP BY COALESCE(mah.REGION_CODE, TO_CHAR(q.SOURCE_LINK)), mah.DISTRICT_CODE""", a), 'q_in')
    for r in _q(client, f"""
        SELECT COALESCE(mah.REGION_CODE, TO_CHAR(q.SOURCE_LINK)) AS REGION_CODE, mah.DISTRICT_CODE, q.STATUS,
               COUNT(*) AS N,
               SUM((CAST(q.REVIEWED_AT AS DATE) - CAST(COALESCE(q.APPLIED_AT, q.CREATED_AT) AS DATE)) * 24) AS HOURS,
               SUM(CASE WHEN CAST(q.REVIEWED_AT AS DATE) - CAST(COALESCE(q.APPLIED_AT, q.CREATED_AT) AS DATE) >= 4 THEN 1 ELSE 0 END) AS LATE
          FROM SARANG_INTAKE_QUEUE q {q_mah}
         WHERE q.STATUS IN ('accepted', 'rejected') AND {_in_range('q.REVIEWED_AT')}
         GROUP BY COALESCE(mah.REGION_CODE, TO_CHAR(q.SOURCE_LINK)), mah.DISTRICT_CODE, q.STATUS""", a):
        if r['status'] == 'accepted':
            add([{**r, 'k': 'q_accepted'}])
            add([{**r, 'k': 'q_wait_hours', 'n': round(float(r['hours'] or 0))}])
            add([{**r, 'k': 'q_late', 'n': r['late']}])  # 신청 4일 지나 이관받음(전체 공개로 넘어간 뒤)
        else:
            add([{**r, 'k': 'q_rejected'}])


def _queue_now(client):
    """지금 이관 대기 중인 건 — 기간과 무관한 현재 상태. 4일 넘게 기다리는 건(전체 공개) 따로."""
    rows = client.query(
        """SELECT COALESCE(mah.REGION_CODE, TO_CHAR(q.SOURCE_LINK)) AS REGION_CODE, mah.DISTRICT_CODE, COUNT(*) AS N,
                  SUM(CASE WHEN SYSDATE - CAST(COALESCE(q.APPLIED_AT, q.CREATED_AT) AS DATE) >= 4 THEN 1 ELSE 0 END) AS OLD
             FROM SARANG_INTAKE_QUEUE q
             LEFT JOIN MEMBER_AFFILIATION_HISTORIES mah ON mah.MEMBER_ID = q.INTRODUCER_MEMBER_ID AND mah.IS_CURRENT = 1
            WHERE q.STATUS IN ('pending', 'submitted')
            GROUP BY COALESCE(mah.REGION_CODE, TO_CHAR(q.SOURCE_LINK)), mah.DISTRICT_CODE""")
    return [{'region': r['region_code'], 'district': r['district_code'], 'waiting': int(r['n']), 'waitingOld': int(r['old'] or 0)}
            for r in rows]


@_admin_view
def erp_weekly(client, body):
    frm, to = _dates(body)
    # 비교 기간 = 같은 길이의 바로 앞 기간 (한 주면 전주, 한 달이면 전달 같은 길이)
    span = (to - frm).days + 1
    prev_frm, prev_to = frm - datetime.timedelta(days=span), to - datetime.timedelta(days=span)
    a = [frm.isoformat(), to.isoformat()]
    jaega = _q(client, f"""
        SELECT * FROM (
          SELECT spi.NAME, COALESCE(im.NAME, m.NAME) AS INTRODUCER_NAME, gm.NAME AS GUIDE_NAME, mah.REGION_CODE, mah.DISTRICT_CODE,
                 al.CREATED_AT AS AT, ROW_NUMBER() OVER (PARTITION BY s.SARANG_ID ORDER BY al.CREATED_AT DESC) AS RN
            FROM SARANG_ACTIVITY_LOGS al
            JOIN SARANG s ON s.SARANG_ID = al.SARANG_ID AND s.DELETED_AT IS NULL
            JOIN SARANG_PERSONAL_INFO spi ON spi.PERSONAL_INFO_ID = s.PERSONAL_INFO_ID
            JOIN MEMBERS m ON m.MEMBER_ID = s.INFLOW_MEMBER_ID
            {_INTRO_MAH}
            LEFT JOIN SARANG_INFLOW_DETAILS sid ON sid.SARANG_ID = s.SARANG_ID
            LEFT JOIN MEMBERS im ON im.MEMBER_ID = sid.INTRODUCER_MEMBER_ID
            LEFT JOIN SARANG_HAB_JAE_YANG h ON h.SARANG_ID = s.SARANG_ID AND h.IS_ACTIVE = 1
            LEFT JOIN MEMBERS gm ON gm.MEMBER_ID = h.GUIDE_MEMBER_ID
           WHERE al.EVENT_TYPE = '재가처리' AND {_in_range('al.CREATED_AT')}
        ) WHERE RN = 1 ORDER BY AT""", a, fetch_limit=2000)
    matches = _q(client, f"""
        SELECT spi.NAME, gm.NAME AS GUIDE_NAME, COALESCE(tm.NAME, h.TEACHER_NAME_OVERRIDE) AS TEACHER_NAME, h.TOOL,
               COALESCE(mrc.LABEL, '진행 예정') AS RESULT_LABEL, mh.MATCH_DEGREE, mh.MATCHED_AT AS AT, mah.REGION_CODE, mah.DISTRICT_CODE
          FROM SARANG_MATCH_HISTORIES mh
          JOIN SARANG s ON s.SARANG_ID = mh.SARANG_ID AND s.DELETED_AT IS NULL
          JOIN SARANG_PERSONAL_INFO spi ON spi.PERSONAL_INFO_ID = s.PERSONAL_INFO_ID
          {_GUIDE_MAH}
          LEFT JOIN MATCH_RESULT_CODES mrc ON mrc.RESULT_CODE = mh.RESULT
          LEFT JOIN SARANG_HAB_JAE_YANG h ON h.SARANG_ID = s.SARANG_ID AND h.IS_ACTIVE = 1
          LEFT JOIN MEMBERS gm ON gm.MEMBER_ID = h.GUIDE_MEMBER_ID
          LEFT JOIN MEMBERS tm ON tm.MEMBER_ID = COALESCE(mh.TEACHER_MEMBER_ID, h.TEACHER_MEMBER_ID)
         WHERE {_in_range('mh.MATCHED_AT')}
         ORDER BY mh.MATCHED_AT""", a, fetch_limit=2000)
    return {
        'range': {'from': frm.isoformat(), 'to': to.isoformat()},
        'prevRange': {'from': prev_frm.isoformat(), 'to': prev_to.isoformat()},
        'cur': _period_metrics(client, frm, to, extended=True),
        'prev': _period_metrics(client, prev_frm, prev_to, extended=True),
        'queueNow': _queue_now(client),
        'jaegaDetails': jaega,
        'matchDetails': matches,
    }


# ── 전환 퍼널 ────────────────────────────────────────────────

@_admin_view
def erp_funnel(client, body):
    """cohort = 기간 안에 유입된 사람들이 지금까지 어디까지 갔나 / event = 기간 안에 각 단계가 몇 건 일어났나."""
    frm, to = _dates(body)
    s = _STAGES_FROM
    cohort = _q(client, f"""
        SELECT mah.REGION_CODE, mah.DISTRICT_CODE, s.RECRUITMENT_TYPE,
               COUNT(*) AS REG,
               SUM(CASE WHEN s.STAGE IN {s['만픽']} OR EXISTS (SELECT 1 FROM TM_LOGS t WHERE t.SARANG_ID = s.SARANG_ID AND t.RESULT = 'MEET_FIX')
                        THEN 1 ELSE 0 END) AS MEET_FIX,
               SUM(CASE WHEN s.STAGE IN {s['합재양']} OR EXISTS (SELECT 1 FROM SARANG_HAB_JAE_YANG h WHERE h.SARANG_ID = s.SARANG_ID)
                        THEN 1 ELSE 0 END) AS HJY,
               SUM(CASE WHEN s.STAGE IN {s['재가']}
                          OR EXISTS (SELECT 1 FROM SARANG_ACTIVITY_LOGS al WHERE al.SARANG_ID = s.SARANG_ID AND al.EVENT_TYPE = '재가처리')
                          OR EXISTS (SELECT 1 FROM SARANG_HAB_JAE_YANG h WHERE h.SARANG_ID = s.SARANG_ID AND h.APPROVAL_STATUS = 'approved')
                        THEN 1 ELSE 0 END) AS JAEGA,
               SUM(CASE WHEN s.STAGE IN {s['상따']}
                          OR EXISTS (SELECT 1 FROM SARANG_MATCH_HISTORIES mh WHERE mh.SARANG_ID = s.SARANG_ID AND mh.RESULT IN {_MET_RESULTS})
                        THEN 1 ELSE 0 END) AS MET,
               SUM(CASE WHEN s.STAGE IN {s['상따']}
                          OR EXISTS (SELECT 1 FROM SARANG_MATCH_HISTORIES mh WHERE mh.SARANG_ID = s.SARANG_ID AND mh.RESULT = 'CONSULT_WIN')
                        THEN 1 ELSE 0 END) AS CONSULT
          FROM SARANG s {_INTRO_MAH}
         WHERE s.DELETED_AT IS NULL AND {_in_range('s.INFLOW_DATE')}
         GROUP BY mah.REGION_CODE, mah.DISTRICT_CODE, s.RECRUITMENT_TYPE""", [frm.isoformat(), to.isoformat()])
    return {
        'cohort': [{'region': r['region_code'], 'district': r['district_code'], 'type': r['recruitment_type'],
                    **{k: int(r[k] or 0) for k in ('reg', 'meet_fix', 'hjy', 'jaega', 'met', 'consult')}} for r in cohort],
        'event': _period_metrics(client, frm, to),
    }
