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

# 기간 안에 유입된 사람(s)이 지금까지 각 단계에 도달했나 — 전환 퍼널·찾기 분석 공용 SELECT 조각
_REACH_SUMS = f"""COUNT(*) AS REG,
               SUM(CASE WHEN s.STAGE IN {_STAGES_FROM['만픽']} OR EXISTS (SELECT 1 FROM TM_LOGS t WHERE t.SARANG_ID = s.SARANG_ID AND t.RESULT = 'MEET_FIX')
                        THEN 1 ELSE 0 END) AS MEET_FIX,
               SUM(CASE WHEN s.STAGE IN {_STAGES_FROM['합재양']} OR EXISTS (SELECT 1 FROM SARANG_HAB_JAE_YANG h WHERE h.SARANG_ID = s.SARANG_ID)
                        THEN 1 ELSE 0 END) AS HJY,
               SUM(CASE WHEN s.STAGE IN {_STAGES_FROM['재가']}
                          OR EXISTS (SELECT 1 FROM SARANG_ACTIVITY_LOGS al WHERE al.SARANG_ID = s.SARANG_ID AND al.EVENT_TYPE = '재가처리')
                          OR EXISTS (SELECT 1 FROM SARANG_HAB_JAE_YANG h WHERE h.SARANG_ID = s.SARANG_ID AND h.APPROVAL_STATUS = 'approved')
                        THEN 1 ELSE 0 END) AS JAEGA,
               SUM(CASE WHEN s.STAGE IN {_STAGES_FROM['상따']}
                          OR EXISTS (SELECT 1 FROM SARANG_MATCH_HISTORIES mh WHERE mh.SARANG_ID = s.SARANG_ID AND mh.RESULT IN {_MET_RESULTS})
                        THEN 1 ELSE 0 END) AS MET,
               SUM(CASE WHEN s.STAGE IN {_STAGES_FROM['상따']}
                          OR EXISTS (SELECT 1 FROM SARANG_MATCH_HISTORIES mh WHERE mh.SARANG_ID = s.SARANG_ID AND mh.RESULT = 'CONSULT_WIN')
                        THEN 1 ELSE 0 END) AS CONSULT"""


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

def _period_metrics(client, frm, to):
    """(지역, 구역)별 기간 내 발생 건수. 사랑이 단위 지표는 사람당 한 번만 셈."""
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

    return [{'region': k[0], 'district': k[1], **v} for k, v in out.items()]


@_admin_view
def erp_weekly(client, body):
    frm, to = _dates(body)
    prev_frm, prev_to = frm - datetime.timedelta(days=7), to - datetime.timedelta(days=7)
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
        'cur': _period_metrics(client, frm, to),
        'prev': _period_metrics(client, prev_frm, prev_to),
        'jaegaDetails': jaega,
        'matchDetails': matches,
    }


# ── 전환 퍼널 ────────────────────────────────────────────────

@_admin_view
def erp_funnel(client, body):
    """cohort = 기간 안에 유입된 사람들이 지금까지 어디까지 갔나 / event = 기간 안에 각 단계가 몇 건 일어났나."""
    frm, to = _dates(body)
    cohort = _q(client, f"""
        SELECT mah.REGION_CODE, mah.DISTRICT_CODE, s.RECRUITMENT_TYPE,
               {_REACH_SUMS}
          FROM SARANG s {_INTRO_MAH}
         WHERE s.DELETED_AT IS NULL AND {_in_range('s.INFLOW_DATE')}
         GROUP BY mah.REGION_CODE, mah.DISTRICT_CODE, s.RECRUITMENT_TYPE""", [frm.isoformat(), to.isoformat()])
    return {
        'cohort': [{'region': r['region_code'], 'district': r['district_code'], 'type': r['recruitment_type'],
                    **{k: int(r[k] or 0) for k in ('reg', 'meet_fix', 'hjy', 'jaega', 'met', 'consult')}} for r in cohort],
        'event': _period_metrics(client, frm, to),
    }


# ── 찾기 분석 ────
_OFFLINE_ROUTES = ('도구노방', '생노', '바따장', '노방', '오프찾')  # 프론트 ErpFind.vue OFFLINE_ROUTES와 같게

# 찾기장소·홍보 학교 이름 묶기 — 같은 곳이 "범계/범계역/범계 로데오", "가천대/가천대학교"처럼 여러 이름으로 적혀서.
# 첫 단어만 쓰고 끝의 역·역사(내)·학교·앞·입구를 뗀 뒤 줄임말을 맞춤. ponytail: 규칙+짧은 별칭표, 새 표기가 쌓이면 별칭표에 추가
_PLACE_ALIAS = {'성대': '성균관대', '중대': '중앙대', '한대앞': '한양대', '한대': '한양대', '마로니에': '혜화', '외대': '한국외대'}
_PLACE_SUFFIXES = ('역사내', '역사', '학교', '입구', '정문', '후문', '역', '앞')


def _norm_place(text):
    name = (text or '').strip().split(' ')[0] if (text or '').strip() else ''
    for _ in range(2):  # "연성대학교앞"처럼 두 번 붙은 것까지
        for suf in _PLACE_SUFFIXES:
            if name.endswith(suf) and len(name) > len(suf) + 1:
                name = name[:-len(suf)]
                break
    return _PLACE_ALIAS.get(name, name) or '(미기록)'

@_admin_view
def erp_find(client, body):
    """기간 안에 찾은 사람을 찾기 경로·도구별로 — 그 뒤 만픽·합재양·재가·만남·상연까지 간 수.
    경로·도구는 합재양 작성 때 저장됨. 합재양 전인 shed 유입(오프)은 도구노방(사쉐)으로 봄."""
    frm, to = _dates(body)
    rows = _q(client, f"""
        SELECT mah.REGION_CODE, mah.DISTRICT_CODE, s.RECRUITMENT_TYPE,
               COALESCE(hj.ROUTE, CASE WHEN sid.SOURCE_LINK IS NOT NULL THEN '도구노방' END) AS ROUTE,
               COALESCE(hj.TOOL, CASE WHEN hj.SARANG_ID IS NULL AND sid.SOURCE_LINK IS NOT NULL THEN '사쉐' END) AS TOOL,
               {_REACH_SUMS}
          FROM SARANG s {_INTRO_MAH}
          LEFT JOIN SARANG_INFLOW_DETAILS sid ON sid.SARANG_ID = s.SARANG_ID
          LEFT JOIN SARANG_HAB_JAE_YANG hj ON hj.SARANG_ID = s.SARANG_ID AND hj.IS_ACTIVE = 1
         WHERE s.DELETED_AT IS NULL AND {_in_range('s.INFLOW_DATE')}
         GROUP BY mah.REGION_CODE, mah.DISTRICT_CODE, s.RECRUITMENT_TYPE,
                  COALESCE(hj.ROUTE, CASE WHEN sid.SOURCE_LINK IS NOT NULL THEN '도구노방' END),
                  COALESCE(hj.TOOL, CASE WHEN hj.SARANG_ID IS NULL AND sid.SOURCE_LINK IS NOT NULL THEN '사쉐' END)""",
        [frm.isoformat(), to.isoformat()], fetch_limit=20000)
    # 온라인은 합재양 때 처음 등록돼 사람 단위 찾기 기록이 없음 → 일일보고 숫자를 씀(2026-10-16 사용자 결정).
    # ONLINE_INTAKE = 온라인 찾기 수, DM = 디엠 보낸 수, QR = 큐알 붙인 수(활동량). 제출 당시 소속 기준
    daily = client.query(
        """SELECT SNAP_REGION_CODE AS REGION_CODE, SNAP_DISTRICT_CODE AS DISTRICT_CODE,
                  SUM(ONLINE_INTAKE_COUNT) AS ONLINE_FOUND, SUM(DM_COUNT) AS DM, SUM(QR_COUNT) AS QR, SUM(TALK_COUNT) AS TALK,
                  -- 홍보 = 그날 적은 홍보 학교 수("학교/경로(도구), 학교…" 쉼표 구분)
                  SUM(CASE WHEN PROMO_LIST IS NULL OR DBMS_LOB.GETLENGTH(PROMO_LIST) = 0 THEN 0 ELSE REGEXP_COUNT(PROMO_LIST, ',') + 1 END) AS PROMO
             FROM DAILY_REPORTS
            WHERE DELETED_AT IS NULL AND REPORT_DATE BETWEEN TO_DATE(:1, 'YYYY-MM-DD') AND TO_DATE(:2, 'YYYY-MM-DD')
            GROUP BY SNAP_REGION_CODE, SNAP_DISTRICT_CODE""",
        [frm.isoformat(), to.isoformat()], fetch_limit=5000)
    # 사람별 — 구역을 펼치면 보여줌. 활동량·온라인 찾기는 일일보고 낸 사람(제출 당시 소속), 오프 찾기는 유입자(현재 소속)
    members = {}

    def member(mid, name, region, district):
        return members.setdefault((mid, region, district), {
            'memberId': mid, 'name': name, 'region': region, 'district': district,
            'talk': 0, 'dm': 0, 'qr': 0, 'promo': 0, 'onlineFound': 0, 'toolStreet': 0, 'offEtc': 0})
    for r in client.query(
        """SELECT dr.MEMBER_ID, m.NAME, dr.SNAP_REGION_CODE AS REGION_CODE, dr.SNAP_DISTRICT_CODE AS DISTRICT_CODE,
                  SUM(dr.ONLINE_INTAKE_COUNT) AS ONLINE_FOUND, SUM(dr.DM_COUNT) AS DM, SUM(dr.QR_COUNT) AS QR, SUM(dr.TALK_COUNT) AS TALK,
                  SUM(CASE WHEN dr.PROMO_LIST IS NULL OR DBMS_LOB.GETLENGTH(dr.PROMO_LIST) = 0 THEN 0 ELSE REGEXP_COUNT(dr.PROMO_LIST, ',') + 1 END) AS PROMO
             FROM DAILY_REPORTS dr JOIN MEMBERS m ON m.MEMBER_ID = dr.MEMBER_ID
            WHERE dr.DELETED_AT IS NULL AND dr.REPORT_DATE BETWEEN TO_DATE(:1, 'YYYY-MM-DD') AND TO_DATE(:2, 'YYYY-MM-DD')
            GROUP BY dr.MEMBER_ID, m.NAME, dr.SNAP_REGION_CODE, dr.SNAP_DISTRICT_CODE""",
            [frm.isoformat(), to.isoformat()], fetch_limit=20000):
        m = member(r['member_id'], r['name'], r['region_code'], r['district_code'])
        for k, col in (('talk', 'talk'), ('dm', 'dm'), ('qr', 'qr'), ('promo', 'promo'), ('onlineFound', 'online_found')):
            m[k] += int(r[col] or 0)
    for r in _q(client, f"""
        SELECT im.MEMBER_ID, im.NAME, mah.REGION_CODE, mah.DISTRICT_CODE,
               COALESCE(hj.ROUTE, CASE WHEN sid.SOURCE_LINK IS NOT NULL THEN '도구노방' END) AS ROUTE, COUNT(*) AS N
          FROM SARANG s {_INTRO_MAH}
          JOIN MEMBERS im ON im.MEMBER_ID = mah.MEMBER_ID
          LEFT JOIN SARANG_INFLOW_DETAILS sid ON sid.SARANG_ID = s.SARANG_ID
          LEFT JOIN SARANG_HAB_JAE_YANG hj ON hj.SARANG_ID = s.SARANG_ID AND hj.IS_ACTIVE = 1
         WHERE s.DELETED_AT IS NULL AND {_in_range('s.INFLOW_DATE')}
         GROUP BY im.MEMBER_ID, im.NAME, mah.REGION_CODE, mah.DISTRICT_CODE, COALESCE(hj.ROUTE, CASE WHEN sid.SOURCE_LINK IS NOT NULL THEN '도구노방' END)""",
            [frm.isoformat(), to.isoformat()], fetch_limit=20000):
        if r['route'] in _OFFLINE_ROUTES:
            m = member(r['member_id'], r['name'], r['region_code'], r['district_code'])
            if r['route'] == '도구노방':
                m['toolStreet'] += int(r['n'])
            else:  # 기타 오프 — 프론트에서 열을 펼치면 경로별(off:생노 등)로 보여줌
                m['offEtc'] += int(r['n'])
                m['off:' + r['route']] = m.get('off:' + r['route'], 0) + int(r['n'])

    # 날짜별 찾기 — 선 그래프용. 온라인 = 일일보고 날짜(REPORT_DATE, 22시 롤오버된 영업일), 오프 = shed로 찾은 날(KST)
    timeline = {}

    def day(d, region, district):
        return timeline.setdefault((d, region, district), {'date': d, 'region': region, 'district': district,
                                                           'onlineFound': 0, 'toolStreet': 0, 'offEtc': 0})
    for r in client.query(
        """SELECT TO_CHAR(REPORT_DATE, 'YYYY-MM-DD') AS D, SNAP_REGION_CODE AS REGION_CODE, SNAP_DISTRICT_CODE AS DISTRICT_CODE,
                  SUM(ONLINE_INTAKE_COUNT) AS N
             FROM DAILY_REPORTS
            WHERE DELETED_AT IS NULL AND REPORT_DATE BETWEEN TO_DATE(:1, 'YYYY-MM-DD') AND TO_DATE(:2, 'YYYY-MM-DD')
            GROUP BY REPORT_DATE, SNAP_REGION_CODE, SNAP_DISTRICT_CODE""",
            [frm.isoformat(), to.isoformat()], fetch_limit=20000):
        day(r['d'], r['region_code'], r['district_code'])['onlineFound'] += int(r['n'] or 0)
    for r in _q(client, f"""
        SELECT TO_CHAR(s.INFLOW_DATE AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD') AS D, mah.REGION_CODE, mah.DISTRICT_CODE,
               COALESCE(hj.ROUTE, CASE WHEN sid.SOURCE_LINK IS NOT NULL THEN '도구노방' END) AS ROUTE, COUNT(*) AS N
          FROM SARANG s {_INTRO_MAH}
          LEFT JOIN SARANG_INFLOW_DETAILS sid ON sid.SARANG_ID = s.SARANG_ID
          LEFT JOIN SARANG_HAB_JAE_YANG hj ON hj.SARANG_ID = s.SARANG_ID AND hj.IS_ACTIVE = 1
         WHERE s.DELETED_AT IS NULL AND {_in_range('s.INFLOW_DATE')}
         GROUP BY TO_CHAR(s.INFLOW_DATE AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD'), mah.REGION_CODE, mah.DISTRICT_CODE,
                  COALESCE(hj.ROUTE, CASE WHEN sid.SOURCE_LINK IS NOT NULL THEN '도구노방' END)""",
            [frm.isoformat(), to.isoformat()], fetch_limit=20000):
        if r['route'] in _OFFLINE_ROUTES:
            day(r['d'], r['region_code'], r['district_code'])['toolStreet' if r['route'] == '도구노방' else 'offEtc'] += int(r['n'])

    # 찾기장소별(shed 유입) — 찾기 수와 그 뒤 만픽·재가까지 간 수
    places = {}
    for r in _q(client, f"""
        SELECT sid.LOCATION, mah.REGION_CODE, mah.DISTRICT_CODE, {_REACH_SUMS}
          FROM SARANG s {_INTRO_MAH}
          JOIN SARANG_INFLOW_DETAILS sid ON sid.SARANG_ID = s.SARANG_ID
         WHERE s.DELETED_AT IS NULL AND sid.SOURCE_LINK IS NOT NULL AND {_in_range('s.INFLOW_DATE')}
         GROUP BY sid.LOCATION, mah.REGION_CODE, mah.DISTRICT_CODE""", [frm.isoformat(), to.isoformat()], fetch_limit=20000):
        key = (_norm_place(r['location']), r['region_code'], r['district_code'])
        p = places.setdefault(key, {'place': key[0], 'region': key[1], 'district': key[2], 'reg': 0, 'meetFix': 0, 'jaega': 0})
        p['reg'] += int(r['reg'] or 0); p['meetFix'] += int(r['meet_fix'] or 0); p['jaega'] += int(r['jaega'] or 0)
    # 홍보 학교별 — 일일보고 홍보 학교 목록. 횟수(보고에 적힌 횟수), 다녀간 사람 수, 마지막 날
    from api.views.daily_report import _parse_promo_list
    schools = {}
    for r in client.query(
        """SELECT dr.MEMBER_ID, dr.SNAP_REGION_CODE AS REGION_CODE, dr.SNAP_DISTRICT_CODE AS DISTRICT_CODE,
                  TO_CHAR(dr.REPORT_DATE, 'YYYY-MM-DD') AS D, DBMS_LOB.SUBSTR(dr.PROMO_LIST, 4000, 1) AS PROMO
             FROM DAILY_REPORTS dr
            WHERE dr.DELETED_AT IS NULL AND dr.PROMO_LIST IS NOT NULL AND DBMS_LOB.GETLENGTH(dr.PROMO_LIST) > 0
              AND dr.REPORT_DATE BETWEEN TO_DATE(:1, 'YYYY-MM-DD') AND TO_DATE(:2, 'YYYY-MM-DD')""",
            [frm.isoformat(), to.isoformat()], fetch_limit=20000):
        for item in _parse_promo_list(r['promo']):
            if not item['school']:
                continue
            key = (_norm_place(item['school']), r['region_code'], r['district_code'])
            sc = schools.setdefault(key, {'school': key[0], 'region': key[1], 'district': key[2], 'visits': 0, 'members': set(), 'last': ''})
            sc['visits'] += 1
            sc['members'].add(r['member_id'])
            sc['last'] = max(sc['last'], r['d'])

    return {'places': list(places.values()),
            'schools': [{**v, 'members': sorted(v['members'])} for v in schools.values()],
            'members': list(members.values()), 'timeline': list(timeline.values()),
            'rows': [{'region': r['region_code'], 'district': r['district_code'], 'type': r['recruitment_type'],
                      'route': r['route'], 'tool': r['tool'],
                      **{k: int(r[k] or 0) for k in ('reg', 'meet_fix', 'hjy', 'jaega', 'met', 'consult')}} for r in rows],
            'daily': [{'region': r['region_code'], 'district': r['district_code'],
                       'onlineFound': int(r['online_found'] or 0), 'dm': int(r['dm'] or 0), 'qr': int(r['qr'] or 0),
                       'talk': int(r['talk'] or 0), 'promo': int(r['promo'] or 0)} for r in daily]}


if __name__ == '__main__':  # 이름 묶기 확인: python -m api.views.erp
    for raw, want in [('범계역', '범계'), ('범계 로데오', '범계'), ('신촌역사내', '신촌'), ('성대 수원', '성균관대'), ('한대앞역', '한양대'),
                      ('연성대학교 앞', '연성대'), ('가천대학교', '가천대'), ('혜화역 4출', '혜화'), ('성대후문', '성균관대'), ('', '(미기록)'), ('한양대에리카', '한양대에리카')]:
        assert _norm_place(raw) == want, (raw, _norm_place(raw), want)
    print('ok')
