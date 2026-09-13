"""assets.js 포팅 대상 — assets 라우트 스텁 (구조만, 로직은 미구현)."""
import hashlib
import json
import logging
import re
import time
import uuid

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from api.auth.gate import get_author_context, require_jwt
from api.clients.data_router import DataRouterClient
from api.telegram.habjaeyang import send_habjaeyang_to_telegram
from api.telegram.matching_dashboard import refresh_matching_dashboard_for_sarang


def _json_body(request):
    try:
        return json.loads(request.body or b'{}')
    except (TypeError, ValueError):
        return {}


def _helper_names_resolver(client, rows, helper_ids_field='helper_member_ids'):
    """조력자는 콤마 구분 MEMBER_ID 목록으로 저장돼서 단순 JOIN으로는 이름을 못 얻음 —
    rows에 등장하는 모든 ID를 한 번에 조회한 뒤, 콤마 목록 문자열 하나를 이름 목록
    문자열로 바꿔주는 함수를 돌려줌."""
    id_set = set()
    for r in rows:
        raw = r.get(helper_ids_field)
        if raw:
            id_set.update(x.strip() for x in raw.split(',') if x.strip())
    name_by_id = {}
    if id_set:
        ids = list(id_set)
        placeholders = ', '.join(f':{i + 1}' for i in range(len(ids)))
        for hr in client.query(f"SELECT MEMBER_ID, NAME FROM MEMBERS WHERE MEMBER_ID IN ({placeholders})", ids):
            name_by_id[hr['member_id']] = hr['name']

    def resolve(raw):
        if not raw:
            return None
        names = [name_by_id.get(x.strip()) for x in raw.split(',') if x.strip()]
        names = [n for n in names if n]
        return ', '.join(names) or None

    return resolve


def _parse_min_label(label):
    """합재양 폼의 '과천/센터까지' select 라벨(예: '1시간 10분', '2시간 이상') → 분(int)."""
    label = str(label or '').strip()
    if not label or label == '미정':
        return None
    if label == '2시간 이상':
        return 120
    m = re.match(r'^(?:(\d+)시간\s*)?(?:(\d+)분)?$', label)
    if not m or not (m.group(1) or m.group(2)):
        return None
    return int(m.group(1) or 0) * 60 + int(m.group(2) or 0)


def _parse_transfer_label(label):
    """'0회'~'3회 이상' → int(count)."""
    label = str(label or '').strip()
    if label == '3회 이상':
        return 3
    m = re.match(r'^(\d+)회$', label)
    return int(m.group(1)) if m else None


def _ox(v):
    return 1 if str(v or '').strip().upper() == 'O' else 0


def _member_id_by_name(client, name):
    """이름 → MEMBERS.MEMBER_ID. FK로 강제하는 저장(합재양/가챠)에서 이름 입력을
    안전하게 ID로 바꿀 때 씀 — 못 찾으면 None(호출부가 그 필드만 비우고 나머지는 저장)."""
    name = str(name or '').strip()
    if not name:
        return None
    row = client.query_one(
        "SELECT MEMBER_ID FROM MEMBERS WHERE NAME = :1 AND DELETED_AT IS NULL FETCH FIRST 1 ROWS ONLY",
        [name],
    )
    return row['member_id'] if row else None


# Shed 통화/접속 상태 — 원본처럼 DB 없이 프로세스 메모리 dict. 원본과 동일한 제약:
# 단일 프로세스 전제(멀티 워커면 워커별로 안 나뉨) — 새로운 제약 아님.
shed_call_state = {}
shed_presence_state = {}
_CALL_TTL_S = 60
_PRESENCE_TTL_S = 12


_APPROVAL_KO = {'pending': '대기', 'approved': '재가', 'rejected': '반려'}
# 결과입력 6옵션의 아이콘 — MatchResultPopup.vue/handleMatchResultPick과 1:1(❌=부정 결과,
# ⭕️=긍정/진행 결과). matchResultDetail 문자열에 그대로 박혀서 프론트 필터/색상 판단에 쓰임.
# MATCH_RESULT_CODES.RESULT_CODE 기준 아이콘 — MatchResultPopup.vue의
# handleMatchResultPick과 1:1(❌=부정 결과, ⭕️=긍정/진행 결과).
_MATCH_RESULT_ICON = {'CANCEL': '❌', 'DELAY': '❌', 'UNFIT': '⭕️', 'DROPOUT': '⭕️', 'SECOND_MEET': '⭕️', 'CONSULT_WIN': '⭕️'}


@csrf_exempt
@require_jwt
def get_assets(request, *args, **kwargs):
    """TM 만남픽스 이후 ~ 매칭 종료까지 다루는 '매칭 절대 지켜!' 화면 데이터.
    services/main/src/routes/assets.js의 GET /get-assets를 새 SARANG 스키마로 재구현.
    프론트(MatchingScreen.vue)는 그대로 두고 예전과 같은 shape(approvalStatus/
    matchResultDetail/habjaeyang/logs/meetings)을 맞춰서 내려줌 — 팀 스코프는 get-shed-
    prospects와 같은 이유로 안 둠(프론트가 팀으로 안 좁힘)."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    client = DataRouterClient()
    rows = client.query(
        """SELECT s.SARANG_ID, s.STAGE, s.AGE, s.GENDER, s.MBTI, s.CREATED_AT,
                  spi.NAME, spi.PHONE, spi.RESIDENCE_STATION,
                  im.NAME AS MANAGER_NAME,
                  hj.HAB_JAE_YANG_ID,
                  TO_CHAR(hj.MATCH_SCHEDULED_AT, 'YYYY-MM-DD') AS MT_DATE,
                  TO_CHAR(hj.MATCH_SCHEDULED_AT, 'HH24:MI') AS MT_TIME,
                  hj.MATCH_LOCATION, hj.SCHOOL_MAJOR_JOB, hj.SCHEDULE, hj.ENVIRONMENT_1Y,
                  hj.APPLICATION_PURPOSE, hj.SELF_IMAGE, hj.DESIRED_IMAGE, hj.CHARACTER_NOTE,
                  hj.ALERT_NOTE, hj.DISTANCE_BURDEN, hj.QNA, hj.ETC,
                  hj.HAS_REPLIED, hj.IS_WINDOW_OPENED, hj.APPROVAL_STATUS, hj.REJECT_REASON,
                  gm.NAME AS GUIDE_NAME, cm.NAME AS CALLER_NAME,
                  COALESCE(tcm.NAME, hj.TEACHER_NAME_OVERRIDE) AS TEACHER_NAME, hj.TEACHER_MEMBER_ID,
                  sid.SOURCE_LINK,
                  COALESCE(TO_CHAR(mf.CREATED_AT AT TIME ZONE 'Asia/Seoul', 'MM/DD HH24:MI'),
                           TO_CHAR(hj.CREATED_AT AT TIME ZONE 'Asia/Seoul', 'MM/DD HH24:MI')) AS PIX_TS
             FROM SARANG s
             JOIN SARANG_PERSONAL_INFO spi ON spi.PERSONAL_INFO_ID = s.PERSONAL_INFO_ID
             JOIN MEMBERS im ON im.MEMBER_ID = s.INFLOW_MEMBER_ID
             LEFT JOIN SARANG_HAB_JAE_YANG hj ON hj.SARANG_ID = s.SARANG_ID AND hj.IS_ACTIVE = 1
             LEFT JOIN MEMBERS gm  ON gm.MEMBER_ID  = hj.GUIDE_MEMBER_ID
             LEFT JOIN MEMBERS cm  ON cm.MEMBER_ID  = hj.CALLER_MEMBER_ID
             LEFT JOIN MEMBERS tcm ON tcm.MEMBER_ID = hj.TEACHER_MEMBER_ID
             LEFT JOIN SARANG_INFLOW_DETAILS sid ON sid.SARANG_ID = s.SARANG_ID
             LEFT JOIN (
               SELECT SARANG_ID, CREATED_AT,
                      ROW_NUMBER() OVER (PARTITION BY SARANG_ID ORDER BY CREATED_AT DESC) AS RN
                 FROM TM_LOGS WHERE RESULT = 'MEET_FIX'
             ) mf ON mf.SARANG_ID = s.SARANG_ID AND mf.RN = 1
            WHERE s.STAGE NOT IN ('유입', '티엠')
              AND s.DELETED_AT IS NULL
              AND s.CREATED_AT >= SYSTIMESTAMP - INTERVAL '90' DAY
            ORDER BY s.CREATED_AT DESC
            FETCH FIRST 1000 ROWS ONLY"""
    )

    sarang_ids = [r['sarang_id'] for r in rows]
    match_rows, tm_rows, activity_rows = [], [], []
    if sarang_ids:
        placeholders = ', '.join(f':{i + 1}' for i in range(len(sarang_ids)))
        match_rows = client.query(
            f"""SELECT smh.SARANG_ID, smh.MATCH_ID, smh.MATCH_DEGREE, smh.ATTEMPT_COUNT,
                       TO_CHAR(smh.MATCHED_AT, 'YYYY-MM-DD') AS MT_DATE,
                       TO_CHAR(smh.MATCHED_AT, 'HH24:MI') AS MT_TIME,
                       smh.MATCH_LOCATION, smh.STATUS, smh.RESULT,
                       mrc.LABEL AS RESULT_LABEL, msrc.LABEL AS SUB_REASON_LABEL,
                       TO_CHAR(smh.CREATED_AT AT TIME ZONE 'Asia/Seoul', 'YY.MM.DD HH24:MI') AS CREATED_TS,
                       smh.CREATED_AT AS SORT_TS
                  FROM SARANG_MATCH_HISTORIES smh
                  LEFT JOIN MATCH_RESULT_CODES mrc ON mrc.RESULT_CODE = smh.RESULT
                  LEFT JOIN MATCH_SUB_REASON_CODES msrc ON msrc.RESULT_CODE = smh.RESULT AND msrc.SUB_CODE = smh.SUB_REASON
                 WHERE smh.SARANG_ID IN ({placeholders})
                 ORDER BY smh.MATCH_DEGREE, smh.ATTEMPT_COUNT""",
            sarang_ids,
        )
        tm_rows = client.query(
            f"""SELECT tl.SARANG_ID, tl.TM_ID AS LOG_ID, trc.LABEL, tl.SUB_REASON, cm.NAME AS ACTOR_NAME,
                       TO_CHAR(tl.CREATED_AT AT TIME ZONE 'Asia/Seoul', 'YY.MM.DD HH24:MI') AS TS,
                       tl.CREATED_AT AS SORT_TS
                  FROM TM_LOGS tl
                  JOIN MEMBERS cm ON cm.MEMBER_ID = tl.CALLER_MEMBER_ID
                  JOIN TM_RESULT_CODES trc ON trc.RESULT_CODE = tl.RESULT
                 WHERE tl.SARANG_ID IN ({placeholders})""",
            sarang_ids,
        )
        activity_rows = client.query(
            f"""SELECT al.SARANG_ID, al.ACTIVITY_ID AS LOG_ID, al.EVENT_TYPE, am.NAME AS ACTOR_NAME,
                       TO_CHAR(al.CREATED_AT AT TIME ZONE 'Asia/Seoul', 'YY.MM.DD HH24:MI') AS TS,
                       al.CREATED_AT AS SORT_TS
                  FROM SARANG_ACTIVITY_LOGS al JOIN MEMBERS am ON am.MEMBER_ID = al.ACTOR_MEMBER_ID
                 WHERE al.SARANG_ID IN ({placeholders})""",
            sarang_ids,
        )

    # MatchingScreen.vue의 formatLogs()가 기대하는 "날짜 | 종류 | 내용 | 작성자" 파이프
    # 3~4단 문자열 포맷 — 구조화된 필드 대신 레거시 그대로 문자열로 합성.
    logs_by_id = {}
    for r in tm_rows:
        content = r['sub_reason'] or r['label']
        line = f"{r['ts']} | {r['label']} | {content} | {r['actor_name']}"
        logs_by_id.setdefault(r['sarang_id'], []).append({'id': r['log_id'], 'source': 'tm', 'text': line, 'sort_ts': r['sort_ts']})
    for r in activity_rows:
        line = f"{r['ts']} | {r['event_type']} | {r['event_type']} | {r['actor_name']}"
        logs_by_id.setdefault(r['sarang_id'], []).append({'id': r['log_id'], 'source': 'activity', 'text': line, 'sort_ts': r['sort_ts']})

    match_by_id = {}
    for r in match_rows:
        match_by_id.setdefault(r['sarang_id'], []).append(r)

    # 밀림/2차만남 로그는 "다음엔 언제로 잡혔는지"를 오른쪽에 같이 보여줌(미정이면
    # 미정으로) — 같은 SARANG_ID 안에서 바로 다음 차수 행의 날짜를 봐야 해서
    # match_by_id가 다 채워진 뒤 2패스로 돎.
    for sid, hist_rows in match_by_id.items():
        for i, r in enumerate(hist_rows):
            if not r['result']:
                continue
            detail = f"{_MATCH_RESULT_ICON.get(r['result'], '')}{r['sub_reason_label'] or r['result_label']}"
            if r['result'] in ('DELAY', 'SECOND_MEET'):
                nxt = hist_rows[i + 1] if i + 1 < len(hist_rows) else None
                if nxt:
                    detail += f" ({nxt['mt_date'] or '미정'})"
            line = f"{r['created_ts']} | 매칭결과 | {detail} | "
            logs_by_id.setdefault(sid, []).append({'id': r['match_id'], 'source': 'match', 'text': line, 'sort_ts': r['sort_ts']})
    for sid in logs_by_id:
        logs_by_id[sid].sort(key=lambda x: x['sort_ts'], reverse=True)

    list_ = []
    for r in rows:
        sid = r['sarang_id']
        hist = match_by_id.get(sid) or []
        latest = hist[-1] if hist else None
        match_result_detail = ''
        if latest and latest['result']:
            match_result_detail = f"{_MATCH_RESULT_ICON.get(latest['result'], '')}{latest['sub_reason_label'] or latest['result_label']}"

        meetings = [{
            'meetingId': m['match_id'],
            'date': m['mt_date'] or '미정',
            'time': m['mt_time'] or '',
            'place': m['match_location'] or '',
            'outcome': (f"{_MATCH_RESULT_ICON.get(m['result'], '')}{m['sub_reason_label'] or m['result_label']}") if m['result'] else None,
            'attended': None,
            # 직전 시도가 2차만남으로 넘어간 결과였으면 이 만남이 바로 그 2차만남 자리.
            'isSecondMeet': bool(i > 0 and hist[i - 1]['result'] == 'SECOND_MEET'),
        } for i, m in enumerate(hist)]
        is_latest_second_meet = bool(len(hist) >= 2 and hist[-2]['result'] == 'SECOND_MEET')

        entries = logs_by_id.get(sid, [])
        has_hj = bool(r['hab_jae_yang_id'])
        list_.append({
            'id': sid,
            'docId': sid,
            'name': r['name'] or '',
            'phone': r['phone'] or '',
            'age': r['age'] or '',
            'gender': r['gender'] or '',
            'residence': r['residence_station'] or '',
            'manager': r['manager_name'] or '',
            'teacher': r['teacher_name'] or '',
            'teacherSabun': r['teacher_member_id'] or '',
            # isShed 판정용(MatchingScreen.vue가 path.startsWith('shed_')로 체크) 겸
            # 실제 유입 링크 번호 표시 — SOURCE_LINK가 없으면(레거시/shed 아닌 유입) 빈 값.
            'path': f"shed_{r['source_link']}" if r['source_link'] else '',
            'tmResultDetail': '만남픽스',
            'matchResultDetail': match_result_detail,
            'approvalStatus': _APPROVAL_KO.get(r['approval_status'], '') if has_hj else '',
            'habjaeyang': {
                'id': r['hab_jae_yang_id'],
                'subName': r['name'] or '',
                'guide': r['guide_name'] or '',
                'tmName': r['caller_name'] or '',
                'gender': r['gender'] or '',
                # 재가 이후엔 SARANG_MATCH_HISTORIES의 최신 시도(밀림/2차만남으로 갱신된
                # 최신 일정)가 있으면 그걸 우선 — 없으면(재가 전) 합재양 최초 일정.
                'mtDate': (latest['mt_date'] or '미정') if latest else (r['mt_date'] or ''),
                'mtTime': (latest['mt_time'] or '') if latest else (r['mt_time'] or ''),
                'mtPlace': (latest['match_location'] or '') if latest else (r['match_location'] or ''),
                'isSecondMeet': is_latest_second_meet if latest else False,
                'mbti': r['mbti'] or '',
                'nearSt': r['residence_station'] or '',
                'job': r['school_major_job'] or '',
                'schedule': r['schedule'] or '',
                'sch': r['schedule'] or '',
                'plan': r['environment_1y'] or '',
                'purpose': r['application_purpose'] or '',
                'selfImage': r['self_image'] or '',
                'trouble': r['desired_image'] or '',
                'att': r['character_note'] or '',
                'wary': r['alert_note'] or '',
                'dist': r['distance_burden'] or '',
                'qna': r['qna'] or '',
                'etc': r['etc'] or '',
                'pixTs': r['pix_ts'] or '',
                'replied': r['has_replied'] == '1',
                'windowOpened': r['is_window_opened'] == '1',
            } if has_hj else {},
            'logs': '\n'.join(x['text'] for x in entries),
            'logEntries': [{'id': x['id'], 'source': x['source'], 'text': x['text']} for x in entries],
            'lastLogTime': entries[0]['text'].split('|')[0].strip() if entries else '',
            'meetings': meetings,
            'finalResult': '',
            'note': {'nextCallDate': '', 'schedule': None},
        })

    return JsonResponse({'success': True, 'list': list_})


@csrf_exempt
@require_jwt
def get_matching_history(request, *args, **kwargs):
    """매칭 절대 지켜!의 "📋 히스토리" 화면 — 날짜 범위로 매칭 시도(SARANG_MATCH_HISTORIES)를
    조회. 내 팀(담당자 소속팀) 것만 — 히스토리는 기간이 넓어서 get-assets(90일/전체)와
    달리 팀으로 좁힘(레거시 정합)."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    start_date = str(body.get('startDate') or '').strip()
    end_date = str(body.get('endDate') or '').strip()
    if not start_date or not end_date:
        return JsonResponse({'success': False, 'meetings': [], 'message': '날짜 범위 필요'}, status=400)

    sabun = request.user['sabun']
    client = DataRouterClient()
    ctx = get_author_context(sabun)
    team_id = ctx['team_id']

    rows = client.query(
        """SELECT smh.MATCH_ID, s.SARANG_ID,
                  TO_CHAR(smh.MATCHED_AT, 'YYYY-MM-DD') AS MT_DATE,
                  TO_CHAR(smh.MATCHED_AT, 'HH24:MI') AS MT_TIME,
                  smh.MATCH_LOCATION, smh.RESULT, mrc.LABEL AS RESULT_LABEL, msrc.LABEL AS SUB_REASON_LABEL,
                  spi.NAME, im.NAME AS MANAGER_NAME, gm.NAME AS GUIDE_NAME,
                  COALESCE(tcm.NAME, hj.TEACHER_NAME_OVERRIDE) AS TEACHER_NAME,
                  hj.APPROVAL_STATUS,
                  CASE WHEN LAG(smh.RESULT) OVER (
                         PARTITION BY smh.SARANG_ID ORDER BY smh.MATCH_DEGREE, smh.ATTEMPT_COUNT
                       ) = 'SECOND_MEET' THEN 1 ELSE 0 END AS IS_SECOND_MEET
             FROM SARANG_MATCH_HISTORIES smh
             JOIN SARANG s ON s.SARANG_ID = smh.SARANG_ID
             JOIN SARANG_PERSONAL_INFO spi ON spi.PERSONAL_INFO_ID = s.PERSONAL_INFO_ID
             JOIN MEMBERS im ON im.MEMBER_ID = s.INFLOW_MEMBER_ID
             JOIN MEMBER_AFFILIATION_HISTORIES mah ON mah.MEMBER_ID = s.INFLOW_MEMBER_ID AND mah.IS_CURRENT = 1
             LEFT JOIN SARANG_HAB_JAE_YANG hj ON hj.SARANG_ID = s.SARANG_ID AND hj.IS_ACTIVE = 1
             LEFT JOIN MEMBERS gm  ON gm.MEMBER_ID  = hj.GUIDE_MEMBER_ID
             LEFT JOIN MEMBERS tcm ON tcm.MEMBER_ID = hj.TEACHER_MEMBER_ID
             LEFT JOIN MATCH_RESULT_CODES mrc ON mrc.RESULT_CODE = smh.RESULT
             LEFT JOIN MATCH_SUB_REASON_CODES msrc ON msrc.RESULT_CODE = smh.RESULT AND msrc.SUB_CODE = smh.SUB_REASON
            WHERE mah.REGION_CODE = :1
              -- LAG()는 팀/날짜로 좁히기 전, 그 사람의 전체 매칭 이력을 봐야 정확함
              -- (직전 시도가 조회 범위 밖 날짜일 수 있어서) — 그래서 WHERE가 아니라
              -- 윈도우 함수 자체는 전체를 보고, 결과 필터링만 날짜로 함.
              AND smh.SARANG_ID IN (
                SELECT SARANG_ID FROM SARANG_MATCH_HISTORIES
                 WHERE MATCHED_AT >= TO_DATE(:2, 'YYYY-MM-DD') AND MATCHED_AT < TO_DATE(:3, 'YYYY-MM-DD') + 1
              )
            ORDER BY s.SARANG_ID, smh.MATCH_DEGREE, smh.ATTEMPT_COUNT""",
        [team_id, start_date, end_date],
    )
    # 위 서브쿼리는 "이 사람이 이 기간에 매칭 이력이 있는지"만 걸러서 SARANG_ID
    # 단위로 전체 이력을 가져옴 — LAG()가 정확해지는 대신, 화면에 낼 땐 실제
    # 날짜 범위 안에 있는 행만 다시 걸러야 함.
    rows = [r for r in rows if r['mt_date'] and start_date <= r['mt_date'] <= end_date]

    meetings = []
    for r in rows:
        outcome = ''
        if r['result']:
            outcome = f"{_MATCH_RESULT_ICON.get(r['result'], '')}{r['sub_reason_label'] or r['result_label']}"
        meetings.append({
            'meetingId': r['match_id'],
            'date': r['mt_date'] or '',
            'time': r['mt_time'] or '',
            # ✌️는 프론트가 표시할 때만 앞에 붙임 — time 자체를 건드리면 화면의
            # 시간순 정렬(localeCompare)이 이모지 때문에 깨짐.
            'isSecondMeet': r['is_second_meet'] == '1',
            'outcome': outcome,
            'place': r['match_location'] or '',
            'docId': r['sarang_id'],
            'name': r['name'] or '',
            'manager': r['manager_name'] or '',
            'guide': r['guide_name'] or '',
            'teacher': r['teacher_name'] or '',
            'approvalStatus': _APPROVAL_KO.get(r['approval_status'], ''),
        })
    return JsonResponse({'success': True, 'meetings': meetings})


@csrf_exempt
def update_manager(request, *args, **kwargs):
    # TODO: services/main/src/routes/assets.js 의 POST /update-manager 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/assets.js"}, status=501)


@csrf_exempt
def update_prospect_info(request, *args, **kwargs):
    # TODO: services/main/src/routes/assets.js 의 POST /update-prospect-info 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/assets.js"}, status=501)


@csrf_exempt
def search_prospects(request, *args, **kwargs):
    # TODO: services/main/src/routes/assets.js 의 POST /search-prospects 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/assets.js"}, status=501)


# 프론트가 보내는 한글 세부사유(reasonType) → (MATCH_RESULT_CODES.RESULT_CODE,
# MATCH_SUB_REASON_CODES.SUB_CODE). sql/11_match_result_codes.sql의 LABEL과 1:1.
_RESULT_SUB_REASON_MAP = {
    '경계취소': ('CANCEL', 'BOUNDARY_CANCEL'), '갈부취소': ('CANCEL', 'CONFLICT_CANCEL'),
    '환경취소': ('CANCEL', 'ENV_CANCEL'), '연두취소': ('CANCEL', 'CONTACT_LOST_CANCEL'),
    '환경비합': ('UNFIT', 'ENV_UNFIT'), '인성비합': ('UNFIT', 'PERSONALITY_UNFIT'),
    '정신질환': ('UNFIT', 'MENTAL_HEALTH'), '건강비합': ('UNFIT', 'HEALTH_UNFIT'),
    '경계탈락': ('DROPOUT', 'BOUNDARY_DROPOUT'), '갈부탈락': ('DROPOUT', 'CONFLICT_DROPOUT'),
}


@csrf_exempt
@require_jwt
def update_match(request, *args, **kwargs):
    """매칭 화면의 다목적 업데이트 — type='status'는 결과입력(취소/비합/탈락/상담따기,
    MatchResultPopup 6옵션 중 밀림/2차만남은 /api/postpone-meeting으로 따로 감),
    type='habjaeyang'은 합재양 보기 팝업의 인라인 필드 편집(editHjField). 따기보고
    (type='ttagi')는 저장할 테이블이 아직 없어 미구현."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    sarang_id = str(body.get('rowIndex') or '').strip()
    edit_type = str(body.get('type') or '')
    data = body.get('data') or {}
    if not sarang_id:
        return JsonResponse({'success': False, 'message': 'rowIndex 필요'}, status=400)

    client = DataRouterClient()

    if edit_type == 'habjaeyang':
        hj = client.query_one(
            "SELECT HAB_JAE_YANG_ID FROM SARANG_HAB_JAE_YANG WHERE SARANG_ID = :1 AND IS_ACTIVE = 1",
            [sarang_id],
        )
        if not hj:
            return JsonResponse({'success': False, 'message': '활성 합재양이 없어요'}, status=404)

        guide_name = str(data.get('guide') or '').strip()
        guide_id = None
        if guide_name:
            guide_id = _member_id_by_name(client, guide_name)
            if not guide_id:
                return JsonResponse({'success': False, 'message': f'인도자 [{guide_name}]이(가) 명단에 없어!'})
        tm_name = str(data.get('tmName') or '').strip()
        caller_id = None
        if tm_name:
            caller_id = _member_id_by_name(client, tm_name)
            if not caller_id:
                return JsonResponse({'success': False, 'message': f'티엠자 [{tm_name}]이(가) 명단에 없어!'})

        client.exec(
            """UPDATE SARANG_HAB_JAE_YANG
                 SET GUIDE_MEMBER_ID = COALESCE(:1, GUIDE_MEMBER_ID), CALLER_MEMBER_ID = COALESCE(:2, CALLER_MEMBER_ID),
                     SCHOOL_MAJOR_JOB = :3, SCHEDULE = :4, ENVIRONMENT_1Y = :5, APPLICATION_PURPOSE = :6,
                     DESIRED_IMAGE = :7, CHARACTER_NOTE = :8, ALERT_NOTE = :9, DISTANCE_BURDEN = :10,
                     QNA = :11, ETC = :12
               WHERE HAB_JAE_YANG_ID = :13""",
            [guide_id, caller_id,
             str(data.get('job') or '').strip() or None, str(data.get('schedule') or data.get('sch') or '').strip() or None,
             str(data.get('plan') or '').strip() or None, str(data.get('purpose') or '').strip() or None,
             str(data.get('trouble') or '').strip() or None, str(data.get('att') or '').strip() or None,
             str(data.get('wary') or '').strip() or None, str(data.get('dist') or '').strip() or None,
             str(data.get('qna') or '').strip() or None, str(data.get('etc') or '').strip() or None,
             hj['hab_jae_yang_id']],
        )
        mbti = str(data.get('mbti') or '').strip()
        if mbti:
            client.exec("UPDATE SARANG SET MBTI = :1 WHERE SARANG_ID = :2", [mbti, sarang_id])
        return JsonResponse({'success': True, 'message': '반영 완료!'})

    if edit_type != 'status':
        return JsonResponse({'success': False, 'message': f'지원 안 되는 type: {edit_type}'}, status=400)

    match_result = str(data.get('matchResult') or '').strip()
    detail = match_result
    for icon in ('❌', '⭕️', '⭕'):
        if detail.startswith(icon):
            detail = detail[len(icon):]
            break
    if detail == '상담따기':
        result_val, sub_reason = 'CONSULT_WIN', None
    else:
        pair = _RESULT_SUB_REASON_MAP.get(detail)
        result_val, sub_reason = pair if pair else (None, None)
    if not result_val:
        return JsonResponse({'success': False, 'message': f'알 수 없는 결과: {match_result}'}, status=400)

    cur = client.query_one(
        """SELECT MATCH_ID FROM SARANG_MATCH_HISTORIES WHERE SARANG_ID = :1 AND RESULT IS NULL
            ORDER BY MATCH_DEGREE DESC, ATTEMPT_COUNT DESC FETCH FIRST 1 ROWS ONLY""",
        [sarang_id],
    )
    if not cur:
        return JsonResponse({'success': False, 'message': '진행 중인 매칭 일정이 없어요'}, status=404)
    client.exec(
        "UPDATE SARANG_MATCH_HISTORIES SET RESULT = :1, SUB_REASON = :2, STATUS = 'FINISHED' WHERE MATCH_ID = :3",
        [result_val, sub_reason, cur['match_id']],
    )
    try:
        refresh_matching_dashboard_for_sarang(client, sarang_id)
    except Exception:
        logging.getLogger('api.views.assets').warning(
            '[update_match:status] matching dashboard refresh failed', exc_info=True,
        )
    return JsonResponse({'success': True, 'message': '결과가 입력됐어!'})


@csrf_exempt
@require_jwt
def submit_result(request, *args, **kwargs):
    """TM 통화/진행 결과 기록. 통화 결과는 TM_LOGS(RESULT), 통화가 아닌 이벤트(문자 발송)는
    SARANG_ACTIVITY_LOGS(EVENT_TYPE)에 남김 — 두 테이블의 CHECK 제약과 1:1로 맞춘 매핑.
    logType='만남픽스'는 SARANG.STAGE 전환(합재양 작성 플로우)까지 얽혀 있어 아직 미구현."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    data = body.get('data') or {}
    sarang_id = str(data.get('rowIndex') or '').strip()
    log_type = data.get('logType')
    log_content = str(data.get('logContent') or '').strip() or None
    if not sarang_id:
        return JsonResponse({'success': False, 'message': 'rowIndex 필요'}, status=400)

    sabun = request.user['sabun']
    client = DataRouterClient()

    # logContent는 이제 한글 사유 텍스트가 아니라 TM_SUB_REASON_CODES.SUB_CODE(예:
    # PERSONALITY_UNFIT)를 프론트에서 그대로 보냄 — RESULT처럼 CHECK 대신 FK로 검증됨.
    TM_RESULT = {'안받음': 'NO_ANSWER', '비합처리': 'UNFIT', '거절처리': 'REJECT', '무효처리': 'INVALID'}
    ACTIVITY_EVENT = {'선문자': '선문자발송', '안받문': '부재중문자발송'}

    if log_type in TM_RESULT:
        client.exec(
            "INSERT INTO TM_LOGS (TM_ID, SARANG_ID, CALLER_MEMBER_ID, RESULT, SUB_REASON) VALUES (:1, :2, :3, :4, :5)",
            [uuid.uuid4().hex.upper(), sarang_id, sabun, TM_RESULT[log_type], log_content],
        )
    elif log_type == '티엠예약':
        next_date = str((data.get('tmNote') or {}).get('nextCallDate') or '').strip() or None
        client.exec(
            """INSERT INTO TM_LOGS (TM_ID, SARANG_ID, CALLER_MEMBER_ID, RESULT, RESERVED_TM_AT)
               VALUES (:1, :2, :3, 'RESERVED_TM',
                       CASE WHEN :4 IS NOT NULL THEN TO_TIMESTAMP(:4, 'YYYY-MM-DD"T"HH24:MI') END)""",
            [uuid.uuid4().hex.upper(), sarang_id, sabun, next_date],
        )
    elif log_type in ACTIVITY_EVENT:
        client.exec(
            "INSERT INTO SARANG_ACTIVITY_LOGS (ACTIVITY_ID, SARANG_ID, ACTOR_MEMBER_ID, EVENT_TYPE) VALUES (:1, :2, :3, :4)",
            [uuid.uuid4().hex.upper(), sarang_id, sabun, ACTIVITY_EVENT[log_type]],
        )
    elif log_type == '만남픽스':
        client.tx([
            {'sql': "INSERT INTO TM_LOGS (TM_ID, SARANG_ID, CALLER_MEMBER_ID, RESULT) VALUES (:1, :2, :3, 'MEET_FIX')",
             'args': [uuid.uuid4().hex.upper(), sarang_id, sabun]},
            {'sql': "UPDATE SARANG SET STAGE = '만픽' WHERE SARANG_ID = :1", 'args': [sarang_id]},
        ])
    elif log_type == '합재양작성':
        hj = data.get('habjaeyang') or {}
        # guide(인도자)는 shed 경로에선 아직 안 정해짐(가챠가 나중에 결정) — 비어있으면 그냥 NULL.
        guide_id = _member_id_by_name(client, hj.get('guide'))
        caller_id = _member_id_by_name(client, hj.get('tmName'))
        mt_date = str(hj.get('mtDate') or '').strip()
        mt_time = str(hj.get('mtTime') or '').strip()
        mt_datetime = f'{mt_date}T{mt_time}' if mt_date and mt_time else None

        hj_args_common = [
            guide_id, caller_id,
            str(hj.get('path') or '').strip() or None, str(hj.get('tool') or '').strip() or None,
            _ox(hj.get('verbalManFix')),
            mt_datetime, mt_datetime, str(hj.get('mtPlace') or '').strip() or None,
            _parse_min_label(hj.get('gwacheonMin')), _parse_transfer_label(hj.get('gwacheonTransfer')),
            _parse_min_label(hj.get('centerMin')), _parse_transfer_label(hj.get('centerTransfer')),
            str(hj.get('job') or '').strip() or None, str(hj.get('sch') or '').strip() or None,
            str(hj.get('plan') or '').strip() or None, str(hj.get('purpose') or '').strip() or None,
            str(hj.get('selfImage') or '').strip() or None, str(hj.get('trouble') or '').strip() or None,
            str(hj.get('att') or '').strip() or None, str(hj.get('wary') or '').strip() or None,
            str(hj.get('dist') or '').strip() or None,
            str(hj.get('qna') or '').strip() or None, str(hj.get('etc') or '').strip() or None,
            _ox(hj.get('centerEnv')), _ox(hj.get('drug')), _ox(hj.get('mental')),
        ]

        existing = client.query_one(
            "SELECT HAB_JAE_YANG_ID FROM SARANG_HAB_JAE_YANG WHERE SARANG_ID = :1 AND IS_ACTIVE = 1",
            [sarang_id],
        )
        if existing:
            hj_stmt = {
                'sql': """UPDATE SARANG_HAB_JAE_YANG
                             SET GUIDE_MEMBER_ID = :1, CALLER_MEMBER_ID = :2, ROUTE = :3, TOOL = :4, IS_VERBAL_MEET = :5,
                                 MATCH_SCHEDULED_AT = CASE WHEN :6 IS NOT NULL THEN TO_TIMESTAMP(:7, 'YYYY-MM-DD"T"HH24:MI') END,
                                 MATCH_LOCATION = :8,
                                 GWACHEON_TRAVEL_TIME = :9, GWACHEON_TRANSFER_COUNT = :10,
                                 CENTER_TRAVEL_TIME = :11, CENTER_TRANSFER_COUNT = :12,
                                 SCHOOL_MAJOR_JOB = :13, SCHEDULE = :14, ENVIRONMENT_1Y = :15, APPLICATION_PURPOSE = :16,
                                 SELF_IMAGE = :17, DESIRED_IMAGE = :18, CHARACTER_NOTE = :19, ALERT_NOTE = :20, DISTANCE_BURDEN = :21,
                                 QNA = :22, ETC = :23,
                                 HAS_CENTER_ENV = :24, IS_TAKING_MEDS = :25, HAS_MENTAL_ILLNESS = :26
                           WHERE HAB_JAE_YANG_ID = :27""",
                'args': hj_args_common + [existing['hab_jae_yang_id']],
            }
        else:
            hj_stmt = {
                'sql': """INSERT INTO SARANG_HAB_JAE_YANG
                            (HAB_JAE_YANG_ID, SARANG_ID, GUIDE_MEMBER_ID, CALLER_MEMBER_ID, ROUTE, TOOL, IS_VERBAL_MEET,
                             MATCH_SCHEDULED_AT, MATCH_LOCATION,
                             GWACHEON_TRAVEL_TIME, GWACHEON_TRANSFER_COUNT, CENTER_TRAVEL_TIME, CENTER_TRANSFER_COUNT,
                             SCHOOL_MAJOR_JOB, SCHEDULE, ENVIRONMENT_1Y, APPLICATION_PURPOSE,
                             SELF_IMAGE, DESIRED_IMAGE, CHARACTER_NOTE, ALERT_NOTE, DISTANCE_BURDEN,
                             QNA, ETC,
                             HAS_CENTER_ENV, IS_TAKING_MEDS, HAS_MENTAL_ILLNESS)
                          VALUES (:1, :2, :3, :4, :5, :6, :7,
                                  CASE WHEN :8 IS NOT NULL THEN TO_TIMESTAMP(:9, 'YYYY-MM-DD"T"HH24:MI') END, :10,
                                  :11, :12, :13, :14,
                                  :15, :16, :17, :18,
                                  :19, :20, :21, :22, :23,
                                  :24, :25, :26, :27, :28)""",
                'args': [uuid.uuid4().hex.upper(), sarang_id] + hj_args_common,
            }

        stmts = [
            hj_stmt,
            {'sql': "INSERT INTO SARANG_ACTIVITY_LOGS (ACTIVITY_ID, SARANG_ID, ACTOR_MEMBER_ID, EVENT_TYPE) VALUES (:1, :2, :3, '합재양작성')",
             'args': [uuid.uuid4().hex.upper(), sarang_id, sabun]},
            {'sql': "UPDATE SARANG SET STAGE = '합재양' WHERE SARANG_ID = :1", 'args': [sarang_id]},
        ]
        mbti = str(hj.get('mbti') or '').strip()
        if mbti:
            stmts.append({'sql': "UPDATE SARANG SET MBTI = :1 WHERE SARANG_ID = :2", 'args': [mbti, sarang_id]})
        gender = str(hj.get('gender') or '').strip()
        if gender:
            stmts.append({'sql': "UPDATE SARANG SET GENDER = :1 WHERE SARANG_ID = :2", 'args': [gender, sarang_id]})
        near_st = str(hj.get('nearSt') or '').strip()
        if near_st:
            stmts.append({
                'sql': """UPDATE SARANG_PERSONAL_INFO SET RESIDENCE_STATION = :1
                           WHERE PERSONAL_INFO_ID = (SELECT PERSONAL_INFO_ID FROM SARANG WHERE SARANG_ID = :2)""",
                'args': [near_st, sarang_id],
            })
        client.tx(stmts)
        try:
            send_habjaeyang_to_telegram(client, sarang_id)
        except Exception:
            logging.getLogger('api.views.assets').warning('[submit_result] telegram send failed', exc_info=True)
    else:
        return JsonResponse({'success': False, 'message': f'아직 지원 안 되는 처리예요: {log_type}'}, status=400)

    return JsonResponse({'success': True})


@csrf_exempt
@require_jwt
def delete_log(request, *args, **kwargs):
    """TM 로그 한 줄 삭제("되돌리기"/개별 로그 × 버튼 공용). 만남픽스(RESULT='MEET_FIX')
    로그를 지우면 SARANG.STAGE도 그 이전 단계('티엠')로 되돌림 — 안 그러면 로그는
    없어졌는데 STAGE만 '만픽'에 남아서 화면엔 계속 "종료" 처리된 채로 보이게 됨."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    sarang_id = str(body.get('rowIndex') or '').strip()
    log_id = str(body.get('id') or '').strip()
    source = body.get('source') or 'tm'
    if not sarang_id or not log_id:
        return JsonResponse({'success': False, 'message': 'rowIndex/id 필요'}, status=400)

    client = DataRouterClient()
    if source == 'tm':
        row = client.query_one("SELECT RESULT FROM TM_LOGS WHERE TM_ID = :1 AND SARANG_ID = :2", [log_id, sarang_id])
        if not row:
            return JsonResponse({'success': False, 'message': '로그를 찾을 수 없어요'}, status=404)
        stmts = [{'sql': "DELETE FROM TM_LOGS WHERE TM_ID = :1", 'args': [log_id]}]
        if row['result'] == 'MEET_FIX':
            stmts.append({'sql': "UPDATE SARANG SET STAGE = '티엠' WHERE SARANG_ID = :1", 'args': [sarang_id]})
        client.tx(stmts)
    elif source == 'match':
        # 매칭결과 로그는 SARANG_MATCH_HISTORIES 행 자체(만남 일정) 삭제가 아니라
        # 입력된 결과만 되돌림 — 그 행은 날짜/장소/교사 정보도 같이 들고 있음.
        affected = client.exec(
            "UPDATE SARANG_MATCH_HISTORIES SET RESULT = NULL, SUB_REASON = NULL, STATUS = 'SCHEDULED' WHERE MATCH_ID = :1 AND SARANG_ID = :2",
            [log_id, sarang_id],
        )
        if not affected:
            return JsonResponse({'success': False, 'message': '로그를 찾을 수 없어요'}, status=404)
    else:
        affected = client.exec(
            "DELETE FROM SARANG_ACTIVITY_LOGS WHERE ACTIVITY_ID = :1 AND SARANG_ID = :2", [log_id, sarang_id]
        )
        if not affected:
            return JsonResponse({'success': False, 'message': '로그를 찾을 수 없어요'}, status=404)

    return JsonResponse({'success': True})


@csrf_exempt
@require_jwt
def toggle_hj_status(request, *args, **kwargs):
    """합재양 답장/창개설 토글 — 매칭 절대 지켜! 카드의 💬/🚪 버튼."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    sarang_id = str(body.get('docId') or '').strip()
    field = str(body.get('field') or '')
    if not sarang_id or field not in ('replied', 'windowOpened'):
        return JsonResponse({'success': False, 'message': 'invalid request'}, status=400)

    client = DataRouterClient()
    new_val = _toggle_hj_field(client, sarang_id, 'HAS_REPLIED' if field == 'replied' else 'IS_WINDOW_OPENED')
    if new_val is None:
        return JsonResponse({'success': False, 'message': '활성 합재양 없음'}, status=404)

    try:
        send_habjaeyang_to_telegram(client, sarang_id)
    except Exception:
        logging.getLogger('api.views.assets').warning('[toggle_hj_status] telegram refresh failed', exc_info=True)

    return JsonResponse({'success': True, 'value': bool(new_val)})


def _toggle_hj_field(client, sarang_id, col):
    """toggle_hj_status(앱 UI)와 텔레그램 인라인 버튼(💬 답장/🚪 창개설)이 공유하는 토글 본체.
    반환: 활성 합재양이 없으면 None, 있으면 새 값(0/1)."""
    cur = client.query_one(
        f"SELECT {col} AS V FROM SARANG_HAB_JAE_YANG WHERE SARANG_ID = :1 AND IS_ACTIVE = 1",
        [sarang_id],
    )
    if not cur:
        return None
    new_val = 0 if cur['v'] == '1' else 1
    client.exec(
        f"UPDATE SARANG_HAB_JAE_YANG SET {col} = :1 WHERE SARANG_ID = :2 AND IS_ACTIVE = 1",
        [new_val, sarang_id],
    )
    return new_val


@csrf_exempt
@require_jwt
def edit_match(request, *args, **kwargs):
    """매칭 절대 지켜! 카드의 날짜수정/섭외자·인도자수정/교사입력 액션. type별 분기는
    MatchingScreen.vue의 editMatchAction/editSubName/editGuideName/handleTeacherSubmit과 1:1."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    sarang_id = str(body.get('rowIndex') or '').strip()
    edit_type = str(body.get('type') or '')
    value = body.get('value')
    if not sarang_id or not edit_type:
        return JsonResponse({'success': False, 'message': 'rowIndex/type 필요'}, status=400)

    client = DataRouterClient()
    hj = client.query_one(
        "SELECT HAB_JAE_YANG_ID FROM SARANG_HAB_JAE_YANG WHERE SARANG_ID = :1 AND IS_ACTIVE = 1",
        [sarang_id],
    )
    if not hj:
        return JsonResponse({'success': False, 'message': '활성 합재양이 없어요'}, status=404)
    hj_id = hj['hab_jae_yang_id']

    if edit_type == 'teacher':
        raw = str(value or '').strip()
        is_other_region = raw.endswith('(타지역)')
        teacher_name = raw[:-5].strip() if is_other_region else raw.split('(')[0].strip()
        teacher_id, override = None, None
        if teacher_name and teacher_name != '-':
            if is_other_region:
                override = raw
            else:
                teacher_id = _member_id_by_name(client, teacher_name)
                if not teacher_id:
                    return JsonResponse({'success': False, 'message': f'사용자 [{teacher_name}] 명단에 없어!'})
        client.exec(
            "UPDATE SARANG_HAB_JAE_YANG SET TEACHER_MEMBER_ID = :1, TEACHER_NAME_OVERRIDE = :2 WHERE HAB_JAE_YANG_ID = :3",
            [teacher_id, override, hj_id],
        )
    elif edit_type == 'date':
        # get-assets는 재가 이후(SARANG_MATCH_HISTORIES 행이 생긴 뒤)엔 표시 날짜를
        # 그 최신 시도 행에서 가져옴 — SARANG_HAB_JAE_YANG.MATCH_SCHEDULED_AT만 고치면
        # 화면엔 반영 안 됨. 열린(RESULT IS NULL) 시도가 있으면 그걸, 없으면(재가 전)
        # 합재양의 최초 일정을 고침.
        dt = str(value or '').replace('T', ' ')[:16]
        open_match = client.query_one(
            """SELECT MATCH_ID FROM SARANG_MATCH_HISTORIES WHERE SARANG_ID = :1 AND RESULT IS NULL
                ORDER BY MATCH_DEGREE DESC, ATTEMPT_COUNT DESC FETCH FIRST 1 ROWS ONLY""",
            [sarang_id],
        )
        if open_match:
            client.exec(
                "UPDATE SARANG_MATCH_HISTORIES SET MATCHED_AT = TO_TIMESTAMP(:1, 'YYYY-MM-DD HH24:MI') WHERE MATCH_ID = :2",
                [dt, open_match['match_id']],
            )
        else:
            client.exec(
                "UPDATE SARANG_HAB_JAE_YANG SET MATCH_SCHEDULED_AT = TO_TIMESTAMP(:1, 'YYYY-MM-DD HH24:MI') WHERE HAB_JAE_YANG_ID = :2",
                [dt, hj_id],
            )
    elif edit_type == 'subGuide':
        parts = str(value or '').split(',')
        sub_name = parts[0].strip() if parts else ''
        guide_name = parts[1].strip() if len(parts) > 1 else ''
        if sub_name:
            client.exec(
                """UPDATE SARANG_PERSONAL_INFO SET NAME = :1
                    WHERE PERSONAL_INFO_ID = (SELECT PERSONAL_INFO_ID FROM SARANG WHERE SARANG_ID = :2)""",
                [sub_name, sarang_id],
            )
        elif guide_name:
            guide_id = _member_id_by_name(client, guide_name)
            if not guide_id:
                return JsonResponse({'success': False, 'message': f'사용자 [{guide_name}] 명단에 없어!'})
            client.exec(
                "UPDATE SARANG_HAB_JAE_YANG SET GUIDE_MEMBER_ID = :1 WHERE HAB_JAE_YANG_ID = :2",
                [guide_id, hj_id],
            )
    elif edit_type == 'gender':
        client.exec("UPDATE SARANG SET GENDER = :1 WHERE SARANG_ID = :2", [str(value or '').strip() or None, sarang_id])
    elif edit_type == 'age':
        client.exec("UPDATE SARANG SET AGE = :1 WHERE SARANG_ID = :2", [str(value or '').strip() or None, sarang_id])
    elif edit_type == 'residence':
        client.exec(
            """UPDATE SARANG_PERSONAL_INFO SET RESIDENCE_STATION = :1
                WHERE PERSONAL_INFO_ID = (SELECT PERSONAL_INFO_ID FROM SARANG WHERE SARANG_ID = :2)""",
            [str(value or '').strip() or None, sarang_id],
        )
    elif edit_type == 'phone':
        phone = str(value or '').strip()
        phone_digits = re.sub(r'\D', '', phone)
        client.exec(
            """UPDATE SARANG_PERSONAL_INFO SET PHONE = :1, PHONE_NORMALIZED = :2
                WHERE PERSONAL_INFO_ID = (SELECT PERSONAL_INFO_ID FROM SARANG WHERE SARANG_ID = :3)""",
            [phone, phone_digits, sarang_id],
        )
    else:
        return JsonResponse({'success': False, 'message': f'지원 안 되는 type: {edit_type}'})

    if edit_type in ('teacher', 'date', 'subGuide'):
        try:
            refresh_matching_dashboard_for_sarang(client, sarang_id)
        except Exception:
            logging.getLogger('api.views.assets').warning('[edit_match] matching dashboard refresh failed', exc_info=True)

    return JsonResponse({'success': True, 'message': '반영 완료!'})


def _set_habjaeyang_approval(client, sarang_id, sabun, enum_val, reason=None):
    """합재양 재가/반려 처리 본체 — update_approval(앱 UI)과 텔레그램 인라인 버튼(🛡️ 재가)이 공유.
    반환: hj row가 없으면 None, 처리했으면 {'habJaeYangId': ...}."""
    hj = client.query_one(
        "SELECT HAB_JAE_YANG_ID FROM SARANG_HAB_JAE_YANG WHERE SARANG_ID = :1 AND IS_ACTIVE = 1",
        [sarang_id],
    )
    if not hj:
        return None

    event_type = '재가처리' if enum_val == 'approved' else '반려처리'
    stmts = [
        {'sql': "UPDATE SARANG_HAB_JAE_YANG SET APPROVAL_STATUS = :1, REJECT_REASON = :2 WHERE HAB_JAE_YANG_ID = :3",
         'args': [enum_val, reason or None, hj['hab_jae_yang_id']]},
        {'sql': "INSERT INTO SARANG_ACTIVITY_LOGS (ACTIVITY_ID, SARANG_ID, ACTOR_MEMBER_ID, EVENT_TYPE, CONTENT) VALUES (:1, :2, :3, :4, :5)",
         'args': [uuid.uuid4().hex.upper(), sarang_id, sabun, event_type, reason or None]},
    ]
    if enum_val == 'approved':
        stmts.append({'sql': "UPDATE SARANG SET STAGE = '재가' WHERE SARANG_ID = :1", 'args': [sarang_id]})
        # 재가 시점에 1차 매칭 시도 행을 만들어둠(합재양에 적힌 만남 일정을 그대로 시드) —
        # 결과입력/날짜수정/교사배정이 여기부터 이 행을 갱신하며 진행됨.
        existing_match = client.query_one(
            "SELECT MATCH_ID FROM SARANG_MATCH_HISTORIES WHERE SARANG_ID = :1", [sarang_id]
        )
        if not existing_match:
            # MATCH_SCHEDULED_AT은 TIMESTAMP라 go-ora로 조회한 문자열을 그대로 다시
            # 바인딩하면 ORA-01843이 남 — INSERT...SELECT로 DB 안에서 직접 복사.
            stmts.append({
                'sql': """INSERT INTO SARANG_MATCH_HISTORIES
                            (MATCH_ID, SARANG_ID, MATCH_DEGREE, ATTEMPT_COUNT, MATCHED_AT, MATCH_LOCATION, STATUS)
                          SELECT :1, SARANG_ID, 1, 1, COALESCE(MATCH_SCHEDULED_AT, SYSTIMESTAMP), MATCH_LOCATION, 'SCHEDULED'
                            FROM SARANG_HAB_JAE_YANG WHERE HAB_JAE_YANG_ID = :2""",
                'args': [uuid.uuid4().hex.upper(), hj['hab_jae_yang_id']],
            })
    client.tx(stmts)
    return {'habJaeYangId': hj['hab_jae_yang_id']}


@csrf_exempt
@require_jwt
def update_approval(request, *args, **kwargs):
    """합재양 재가/반려 처리 — 매칭 절대 지켜! 🔒 버튼 뒤의 결정 팝업(showApprDecisionPopup)."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    sarang_id = str(body.get('rowIndex') or '').strip()
    status_ko = str(body.get('status') or '').strip()
    reason = str(body.get('reason') or '').strip()[:500]
    status_map = {'재가': 'approved', '반려': 'rejected'}
    enum_val = status_map.get(status_ko)
    if not sarang_id or not enum_val:
        return JsonResponse({'success': False, 'message': 'rowIndex, status 필요'}, status=400)

    sabun = request.user['sabun']
    client = DataRouterClient()
    if _set_habjaeyang_approval(client, sarang_id, sabun, enum_val, reason) is None:
        return JsonResponse({'success': False, 'message': '활성 합재양이 없어요'}, status=404)

    try:
        send_habjaeyang_to_telegram(client, sarang_id)
    except Exception:
        logging.getLogger('api.views.assets').warning('[update_approval] telegram refresh failed', exc_info=True)

    if enum_val == 'approved':
        try:
            refresh_matching_dashboard_for_sarang(client, sarang_id)
        except Exception:
            logging.getLogger('api.views.assets').warning('[update_approval] matching dashboard refresh failed', exc_info=True)

    return JsonResponse({'success': True, 'message': f'{status_ko} 처리 완료!'})


@csrf_exempt
@require_jwt
def postpone_meeting(request, *args, **kwargs):
    """결과입력의 밀림/2차만남 처리 — 현재 열린(RESULT IS NULL) 매칭 시도를 마무리하고
    새 시도 행을 추가. SARANG_MATCH_HISTORIES는 append-only라 밀림은 같은 차수 안에서
    ATTEMPT_COUNT+1, 2차만남은 새 차수(MATCH_DEGREE+1)로 넘어감(테이블 자체 설계).
    날짜를 아직 안 정했으면('미정' 체크) MATCHED_AT을 NULL로 둬서 프론트가 '미정'
    그룹으로 묶게 함."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    sarang_id = str(body.get('rowIndex') or '').strip()
    log_type = str(body.get('logType') or '')
    new_date = str(body.get('newDate') or '').strip()
    reason = str(body.get('logContent') or '').strip()
    if not sarang_id or log_type not in ('밀림처리', '2차만남'):
        return JsonResponse({'success': False, 'message': 'rowIndex/logType 필요'}, status=400)

    result_code = 'DELAY' if log_type == '밀림처리' else 'SECOND_MEET'
    sabun = request.user['sabun']
    client = DataRouterClient()

    cur = client.query_one(
        """SELECT MATCH_ID, MATCH_DEGREE, ATTEMPT_COUNT, TEACHER_MEMBER_ID, MATCH_LOCATION
             FROM SARANG_MATCH_HISTORIES WHERE SARANG_ID = :1 AND RESULT IS NULL
            ORDER BY MATCH_DEGREE DESC, ATTEMPT_COUNT DESC FETCH FIRST 1 ROWS ONLY""",
        [sarang_id],
    )
    if not cur:
        return JsonResponse({'success': False, 'message': '진행 중인 매칭 일정이 없어요'}, status=404)

    if log_type == '밀림처리':
        next_degree, next_attempt = int(cur['match_degree']), int(cur['attempt_count']) + 1
    else:
        next_degree, next_attempt = int(cur['match_degree']) + 1, 1

    stmts = [
        {'sql': "UPDATE SARANG_MATCH_HISTORIES SET RESULT = :1, STATUS = 'FINISHED' WHERE MATCH_ID = :2",
         'args': [result_code, cur['match_id']]},
        {'sql': "INSERT INTO SARANG_ACTIVITY_LOGS (ACTIVITY_ID, SARANG_ID, ACTOR_MEMBER_ID, EVENT_TYPE, CONTENT) VALUES (:1, :2, :3, :4, :5)",
         'args': [uuid.uuid4().hex.upper(), sarang_id, sabun, log_type, reason or None]},
    ]
    if new_date and new_date != '미정':
        dt = new_date.replace('T', ' ')[:16]
        stmts.append({
            'sql': """INSERT INTO SARANG_MATCH_HISTORIES
                        (MATCH_ID, SARANG_ID, MATCH_DEGREE, ATTEMPT_COUNT, MATCHED_AT, MATCH_LOCATION, TEACHER_MEMBER_ID, STATUS)
                      VALUES (:1, :2, :3, :4, TO_TIMESTAMP(:5, 'YYYY-MM-DD HH24:MI'), :6, :7, 'SCHEDULED')""",
            'args': [uuid.uuid4().hex.upper(), sarang_id, next_degree, next_attempt, dt, cur['match_location'], cur['teacher_member_id']],
        })
    else:
        stmts.append({
            'sql': """INSERT INTO SARANG_MATCH_HISTORIES
                        (MATCH_ID, SARANG_ID, MATCH_DEGREE, ATTEMPT_COUNT, MATCHED_AT, MATCH_LOCATION, TEACHER_MEMBER_ID, STATUS)
                      VALUES (:1, :2, :3, :4, NULL, :5, :6, 'SCHEDULED')""",
            'args': [uuid.uuid4().hex.upper(), sarang_id, next_degree, next_attempt, cur['match_location'], cur['teacher_member_id']],
        })
    client.tx(stmts)

    try:
        refresh_matching_dashboard_for_sarang(client, sarang_id)
    except Exception:
        logging.getLogger('api.views.assets').warning('[postpone_meeting] matching dashboard refresh failed', exc_info=True)

    return JsonResponse({'success': True, 'message': f'{log_type} 처리 완료!'})


@csrf_exempt
def clone_row(request, *args, **kwargs):
    # TODO: services/main/src/routes/assets.js 의 POST /clone-row 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/assets.js"}, status=501)


@csrf_exempt
def get_center_assets(request, *args, **kwargs):
    # TODO: services/main/src/routes/assets.js 의 POST /get-center-assets 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/assets.js"}, status=501)


@csrf_exempt
@require_jwt
def submit_habjaeyang_new(request, *args, **kwargs):
    """기존 TM 리드 없이 합재양 작성 화면에서 바로 새 사랑이(SARANG)를 만드는 경로.
    submit_result의 '합재양작성' 분기(기존 SARANG_ID가 있는 경우)와 짝을 이룸 —
    컬럼 매핑은 그쪽과 동일하게 맞춤. ponytail: 레거시에 있던 동일 전화번호
    중복섭외 감지/팝업(habjaeyang-dup-resolve)은 이 스키마엔 PROSPECTS.IS_DROPPED가
    없어서(get_shed_prospects 주석 참고) 표현 방식부터 다시 설계해야 함 — 일단 항상
    새로 등록만 하고, 필요해지면 추가."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    hj = (body.get('data') or {}).get('habjaeyang') or {}

    name = str(hj.get('subName') or '').strip()
    phone_raw = str(hj.get('contact') or '').strip()
    phone_normalized = re.sub(r'[^0-9]', '', phone_raw)
    if not name:
        return JsonResponse({'success': False, 'message': '이름을 입력해줘!'}, status=400)
    if len(phone_normalized) < 10:
        return JsonResponse({'success': False, 'message': '연락처를 올바르게 입력해줘!'}, status=400)

    sabun = request.user['sabun']
    client = DataRouterClient()

    guide_id = _member_id_by_name(client, hj.get('guide'))
    caller_id = _member_id_by_name(client, hj.get('tmName'))
    inflow_member_id = guide_id or sabun

    path_val = str(hj.get('path') or '').strip() or None
    tool_val = str(hj.get('tool') or '').strip() or None
    recruitment_type = 'ONLINE'
    if path_val:
        path_cfg = client.query_one(
            "SELECT ON_OFF FROM PATH_CONFIGS WHERE NAME = :1 AND DELETED_AT IS NULL FETCH FIRST 1 ROWS ONLY",
            [path_val],
        )
        if path_cfg:
            recruitment_type = path_cfg['on_off'].upper()

    mt_date = str(hj.get('mtDate') or '').strip()
    mt_time = str(hj.get('mtTime') or '').strip()
    mt_datetime = f'{mt_date}T{mt_time}' if mt_date and mt_time else None

    age_raw = str(hj.get('age') or '').strip()
    age_num = int(age_raw) if age_raw.isdigit() else None
    gender = str(hj.get('gender') or '').strip()
    gender = gender if gender in ('남', '여') else None
    mbti = str(hj.get('mbti') or '').strip() or None

    personal_info_id = hashlib.sha256(f'{name}|{phone_normalized}'.encode('utf-8')).hexdigest()
    sarang_id = uuid.uuid4().hex.upper()

    stmts = []
    existing_pi = client.query_one(
        "SELECT PERSONAL_INFO_ID FROM SARANG_PERSONAL_INFO WHERE PERSONAL_INFO_ID = :1", [personal_info_id]
    )
    if not existing_pi:
        stmts.append({
            'sql': """INSERT INTO SARANG_PERSONAL_INFO (PERSONAL_INFO_ID, NAME, PHONE, PHONE_NORMALIZED, RESIDENCE_STATION)
                      VALUES (:1, :2, :3, :4, :5)""",
            'args': [personal_info_id, name, phone_raw, phone_normalized, str(hj.get('nearSt') or '').strip() or None],
        })

    stmts.append({
        'sql': """INSERT INTO SARANG
                    (SARANG_ID, PERSONAL_INFO_ID, INFLOW_MEMBER_ID, AGE, GENDER, MBTI, STAGE,
                     RECRUITMENT_TYPE, INFLOW_DATE, CURRENT_PROCESS, CREATED_BY, UPDATED_BY)
                  VALUES (:1, :2, :3, :4, :5, :6, '합재양', :7, SYSTIMESTAMP, '합재양', :8, :8)""",
        'args': [sarang_id, personal_info_id, inflow_member_id, age_num, gender, mbti, recruitment_type, sabun],
    })

    stmts.append({
        'sql': """INSERT INTO SARANG_HAB_JAE_YANG
                    (HAB_JAE_YANG_ID, SARANG_ID, GUIDE_MEMBER_ID, CALLER_MEMBER_ID, ROUTE, TOOL, IS_VERBAL_MEET,
                     MATCH_SCHEDULED_AT, MATCH_LOCATION,
                     GWACHEON_TRAVEL_TIME, GWACHEON_TRANSFER_COUNT, CENTER_TRAVEL_TIME, CENTER_TRANSFER_COUNT,
                     SCHOOL_MAJOR_JOB, SCHEDULE, ENVIRONMENT_1Y, APPLICATION_PURPOSE,
                     SELF_IMAGE, DESIRED_IMAGE, CHARACTER_NOTE, ALERT_NOTE, DISTANCE_BURDEN,
                     QNA, ETC,
                     HAS_CENTER_ENV, IS_TAKING_MEDS, HAS_MENTAL_ILLNESS)
                  VALUES (:1, :2, :3, :4, :5, :6, :7,
                          CASE WHEN :8 IS NOT NULL THEN TO_TIMESTAMP(:9, 'YYYY-MM-DD"T"HH24:MI') END, :10,
                          :11, :12, :13, :14,
                          :15, :16, :17, :18,
                          :19, :20, :21, :22, :23,
                          :24, :25, :26, :27, :28)""",
        'args': [
            uuid.uuid4().hex.upper(), sarang_id, guide_id, caller_id, path_val, tool_val, _ox(hj.get('verbalManFix')),
            mt_datetime, mt_datetime, str(hj.get('mtPlace') or '').strip() or None,
            _parse_min_label(hj.get('gwacheonMin')), _parse_transfer_label(hj.get('gwacheonTransfer')),
            _parse_min_label(hj.get('centerMin')), _parse_transfer_label(hj.get('centerTransfer')),
            str(hj.get('job') or '').strip() or None, str(hj.get('sch') or '').strip() or None,
            str(hj.get('plan') or '').strip() or None, str(hj.get('purpose') or '').strip() or None,
            str(hj.get('selfImage') or '').strip() or None, str(hj.get('trouble') or '').strip() or None,
            str(hj.get('att') or '').strip() or None, str(hj.get('wary') or '').strip() or None,
            str(hj.get('dist') or '').strip() or None,
            str(hj.get('qna') or '').strip() or None, str(hj.get('etc') or '').strip() or None,
            _ox(hj.get('centerEnv')), _ox(hj.get('drug')), _ox(hj.get('mental')),
        ],
    })

    stmts.append({
        'sql': "INSERT INTO SARANG_ACTIVITY_LOGS (ACTIVITY_ID, SARANG_ID, ACTOR_MEMBER_ID, EVENT_TYPE) VALUES (:1, :2, :3, '합재양작성')",
        'args': [uuid.uuid4().hex.upper(), sarang_id, sabun],
    })

    client.tx(stmts)

    try:
        send_habjaeyang_to_telegram(client, sarang_id)
    except Exception:
        logging.getLogger('api.views.assets').warning('[submit_habjaeyang_new] telegram send failed', exc_info=True)

    return JsonResponse({'success': True, 'message': '✅ 저장 완료!', 'prospectId': sarang_id})


@csrf_exempt
def habjaeyang_dup_resolve(request, *args, **kwargs):
    # TODO: services/main/src/routes/assets.js 의 POST /habjaeyang-dup-resolve 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/assets.js"}, status=501)


@csrf_exempt
@require_jwt
def shed_call_status(request, *args, **kwargs):
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    now = time.time()
    body = _json_body(request)
    calling_pid = str((body.get('data') or {}).get('callingProspectId') or '').strip().upper()
    if calling_pid and calling_pid in shed_call_state:
        shed_call_state[calling_pid]['lastHeartbeat'] = now
    for pid in list(shed_call_state.keys()):
        entry = shed_call_state[pid]
        hb = entry.get('lastHeartbeat') or entry.get('startedAt') or 0
        if now - hb > _CALL_TTL_S:
            del shed_call_state[pid]

    sabun = request.user.get('sabun')
    if sabun:
        shed_presence_state[sabun] = {'name': request.user.get('name'), 'lastHeartbeat': now}
    for s in list(shed_presence_state.keys()):
        if now - shed_presence_state[s]['lastHeartbeat'] > _PRESENCE_TTL_S:
            del shed_presence_state[s]

    return JsonResponse({'success': True, 'calls': shed_call_state, 'presence': shed_presence_state})


@csrf_exempt
@require_jwt
def shed_presence_leave(request, *args, **kwargs):
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    shed_presence_state.pop(request.user.get('sabun'), None)
    return JsonResponse({'success': True})


@csrf_exempt
@require_jwt
def shed_call_start(request, *args, **kwargs):
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    body = _json_body(request)
    prospect_id = str((body.get('data') or {}).get('prospectId') or '').strip().upper()
    if not prospect_id:
        return JsonResponse({'success': False, 'message': 'prospectId 필요'}, status=400)
    ctx = get_author_context(request.user['sabun'])
    shed_call_state[prospect_id] = {
        'callerName': ctx['name'], 'callerSabun': ctx['sabun'], 'startedAt': time.time(),
    }
    return JsonResponse({'success': True})


@csrf_exempt
@require_jwt
def shed_call_end(request, *args, **kwargs):
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    body = _json_body(request)
    prospect_id = str((body.get('data') or {}).get('prospectId') or '').strip().upper()
    shed_call_state.pop(prospect_id, None)
    return JsonResponse({'success': True})


@csrf_exempt
def shed_note_save(request, *args, **kwargs):
    # TODO: services/main/src/routes/assets.js 의 POST /shed-note-save 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/assets.js"}, status=501)


@csrf_exempt
@require_jwt
def get_tm_script(request, *args, **kwargs):
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    body = _json_body(request)
    script_type = str(body.get('scriptType') or 'tm')
    row = DataRouterClient().query_one(
        'SELECT SCRIPT_MODE, SCRIPT_TEXT FROM USER_TM_SCRIPTS WHERE SABUN = :1 AND SCRIPT_TYPE = :2',
        [request.user['sabun'], script_type],
    )
    if not row:
        return JsonResponse({'success': True, 'mode': 'default', 'text': ''})
    return JsonResponse({'success': True, 'mode': row.get('script_mode') or 'default', 'text': row.get('script_text') or ''})


@csrf_exempt
@require_jwt
def save_tm_script(request, *args, **kwargs):
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    body = _json_body(request)
    data = body.get('data') or {}
    sabun = request.user['sabun']
    script_type = str(data.get('scriptType') or 'tm')
    mode = str(data.get('mode') or 'default')
    text = str(data.get('text') or '')

    # 원본은 MERGE 한 방(8개 distinct bind — go-ora MERGE 버그 패턴과는 다르지만,
    # api/auth/passkey.py 의 set_hash()에서 이미 검증된 update-then-insert로 통일).
    client = DataRouterClient()
    affected = client.exec(
        'UPDATE USER_TM_SCRIPTS SET SCRIPT_MODE = :1, SCRIPT_TEXT = :2, UPDATED_AT = SYSTIMESTAMP '
        'WHERE SABUN = :3 AND SCRIPT_TYPE = :4',
        [mode, text, sabun, script_type],
    )
    if not affected:
        client.exec(
            'INSERT INTO USER_TM_SCRIPTS (SABUN, SCRIPT_TYPE, SCRIPT_MODE, SCRIPT_TEXT) VALUES (:1, :2, :3, :4)',
            [sabun, script_type, mode, text],
        )
    return JsonResponse({'success': True})


@csrf_exempt
@require_jwt
def shed_register(request, *args, **kwargs):
    """SARANG_INTAKE_QUEUE 수락 처리 — pending 항목을 SARANG_PERSONAL_INFO/
    SARANG/SARANG_INFLOW_DETAILS로 승격. 수락한 담당자가 INFLOW_MEMBER_ID가 됨."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    intake_id = str(body.get('intakeId') or '').strip()
    if not intake_id:
        return JsonResponse({'success': False, 'message': 'intakeId 필요'}, status=400)

    client = DataRouterClient()
    intake = client.query_one(
        "SELECT * FROM SARANG_INTAKE_QUEUE WHERE INTAKE_ID = :1", [intake_id]
    )
    if not intake:
        return JsonResponse({'success': False, 'message': '대기열 항목을 찾을 수 없습니다'}, status=404)
    if intake['status'] != 'submitted':
        return JsonResponse({'success': False, 'message': f"아직 이관 요청되지 않았거나 이미 처리된 항목입니다({intake['status']})"}, status=400)

    sabun = request.user['sabun']
    personal_info_id = hashlib.sha256(f"{intake['name']}|{intake['phone_normalized']}".encode('utf-8')).hexdigest()
    sarang_id = uuid.uuid4().hex.upper()

    stmts = []
    existing_pi = client.query_one(
        "SELECT PERSONAL_INFO_ID FROM SARANG_PERSONAL_INFO WHERE PERSONAL_INFO_ID = :1", [personal_info_id]
    )
    if not existing_pi:
        stmts.append({
            'sql': """INSERT INTO SARANG_PERSONAL_INFO (PERSONAL_INFO_ID, NAME, PHONE, PHONE_NORMALIZED)
                      VALUES (:1, :2, :3, :4)""",
            'args': [personal_info_id, intake['name'], intake['phone'], intake['phone_normalized']],
        })
    stmts.append({
        'sql': """INSERT INTO SARANG
                    (SARANG_ID, PERSONAL_INFO_ID, INFLOW_MEMBER_ID, AGE, MBTI, STAGE,
                     RECRUITMENT_TYPE, INFLOW_DATE, CREATED_BY, UPDATED_BY)
                  VALUES (:1, :2, :3, :4, :5, '유입', 'OFFLINE', SYSTIMESTAMP, :6, :6)""",
        'args': [sarang_id, personal_info_id, sabun, intake['age'], intake['mbti'], sabun],
    })
    # TM_RESERVED_AT은 TIMESTAMP 컬럼 — go-ora로 조회한 문자열을 그대로 다시 바인딩하면
    # ORA-01843(not a valid month)이 나서, DB 안에서 직접 복사(INSERT ... SELECT)함.
    stmts.append({
        'sql': """INSERT INTO SARANG_INFLOW_DETAILS
                    (SARANG_ID, REGION_NAME, REACTION, LOCATION, ENV, INTRODUCER_MEMBER_ID, HELPER_MEMBER_IDS, TM_RESERVED_AT, SOURCE_LINK)
                  SELECT :1, REGION_NAME, REACTION, LOCATION, ENV, INTRODUCER_MEMBER_ID, HELPER_MEMBER_IDS, TM_RESERVED_AT, SOURCE_LINK
                    FROM SARANG_INTAKE_QUEUE WHERE INTAKE_ID = :2""",
        'args': [sarang_id, intake_id],
    })
    stmts.append({
        'sql': """UPDATE SARANG_INTAKE_QUEUE SET STATUS = 'accepted', REVIEWED_BY_MEMBER_ID = :1, REVIEWED_AT = SYSTIMESTAMP
                  WHERE INTAKE_ID = :2""",
        'args': [sabun, intake_id],
    })
    client.tx(stmts)
    return JsonResponse({'success': True, 'sarangId': sarang_id})


@csrf_exempt
def shed_reject_duplicate(request, *args, **kwargs):
    # TODO: services/main/src/routes/assets.js 의 POST /shed-reject-duplicate 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/assets.js"}, status=501)


@csrf_exempt
@require_jwt
def get_shed_prospects(request, *args, **kwargs):
    """schema-spec.md(Sarang Domain) 기준 재구현. 질적 찾기(2/4/6팀)·선한 양치기
    (1/3/5팀)는 프론트에서 inflow_member의 현재 소속팀으로 묶어서 보여주는
    구분이라(같은 화면에 3개 팀이 같이 보임), 서버는 팀으로 좁히지 않고 전체를
    반환하면서 각 항목에 team을 실어준다.
    SARANG_INFLOW_DETAILS를 INNER JOIN — 이 화면은 사쉐 번호찾(shed_register)으로
    들어온 건만 다루는 화면이라, 합재양 작성에서 바로 등록된 건(그 테이블에 행이
    안 생김)은 여기서 아예 빠져야 함."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    client = DataRouterClient()
    rows = client.query(
        """SELECT s.SARANG_ID, s.STAGE, s.CURRENT_PROCESS, s.AGE, s.MBTI,
                  s.RECRUITMENT_TYPE, s.INFLOW_DATE, s.CREATED_AT,
                  spi.NAME, spi.PHONE, spi.RESIDENCE_STATION,
                  m.NAME AS INFLOW_MEMBER_NAME, mah.REGION_CODE AS TEAM,
                  sid.REGION_NAME, sid.REACTION, sid.LOCATION, sid.ENV,
                  im.NAME AS INTRODUCER_NAME, sid.HELPER_MEMBER_IDS, sid.TM_RESERVED_AT,
                  shjy.HAB_JAE_YANG_ID,
                  gm.NAME AS GUIDE_NAME, cm.NAME AS CALLER_NAME, tcm.NAME AS TEACHER_NAME
             FROM SARANG s
             JOIN SARANG_PERSONAL_INFO spi ON spi.PERSONAL_INFO_ID = s.PERSONAL_INFO_ID
             JOIN MEMBERS m ON m.MEMBER_ID = s.INFLOW_MEMBER_ID
             JOIN MEMBER_AFFILIATION_HISTORIES mah
               ON mah.MEMBER_ID = s.INFLOW_MEMBER_ID AND mah.IS_CURRENT = 1
             JOIN SARANG_INFLOW_DETAILS sid ON sid.SARANG_ID = s.SARANG_ID
             LEFT JOIN MEMBERS im ON im.MEMBER_ID = sid.INTRODUCER_MEMBER_ID
             LEFT JOIN SARANG_HAB_JAE_YANG shjy ON shjy.SARANG_ID = s.SARANG_ID AND shjy.IS_ACTIVE = 1
             LEFT JOIN MEMBERS gm  ON gm.MEMBER_ID  = shjy.GUIDE_MEMBER_ID
             LEFT JOIN MEMBERS cm  ON cm.MEMBER_ID  = shjy.CALLER_MEMBER_ID
             LEFT JOIN MEMBERS tcm ON tcm.MEMBER_ID = shjy.TEACHER_MEMBER_ID
            WHERE s.DELETED_AT IS NULL
            ORDER BY s.CREATED_AT DESC""",
    )

    _helper_names = _helper_names_resolver(client, rows)

    sarang_ids = [r['sarang_id'] for r in rows]
    # 타임라인 맨 마지막(가장 오래된 항목)에 유입 자체를 하나의 로그처럼 넣어줌 —
    # "누가 유입했는지"가 통화기록보다 먼저(시간상 가장 앞) 보이도록. INFLOW_MEMBER_NAME은
    # "이관받기"를 클릭한 Ddochi 담당자라 다른 개념 — 실제 유입자(shed에서 찾은 사람)는
    # INTRODUCER_NAME이므로 그걸 우선 쓰고, 없을 때만(레거시 데이터 등) 담당자로 대체.
    timeline_by_id = {
        r['sarang_id']: [{'id': f"{r['sarang_id']}-inflow", 'label': '유입', 'category': None, 'source': 'inflow',
                           'actorName': r['introducer_name'] or r['inflow_member_name'], 'createdAt': r['inflow_date']}]
        for r in rows
    }
    call_rows = []
    if sarang_ids:
        placeholders = ', '.join(f':{i + 1}' for i in range(len(sarang_ids)))
        call_rows = client.query(
            f"""SELECT tl.SARANG_ID, tl.TM_ID AS LOG_ID, tl.RESULT, trc.LABEL, tl.CREATED_AT, cm.NAME AS ACTOR_NAME
                  FROM TM_LOGS tl
                  JOIN MEMBERS cm ON cm.MEMBER_ID = tl.CALLER_MEMBER_ID
                  JOIN TM_RESULT_CODES trc ON trc.RESULT_CODE = tl.RESULT
                 WHERE tl.SARANG_ID IN ({placeholders})""",
            sarang_ids,
        )
        activity_rows = client.query(
            f"""SELECT al.SARANG_ID, al.ACTIVITY_ID AS LOG_ID, al.EVENT_TYPE AS LABEL, al.CREATED_AT, am.NAME AS ACTOR_NAME
                  FROM SARANG_ACTIVITY_LOGS al JOIN MEMBERS am ON am.MEMBER_ID = al.ACTOR_MEMBER_ID
                 WHERE al.SARANG_ID IN ({placeholders})""",
            sarang_ids,
        )
        # 프론트가 category로 특정 로그 존재 여부를 판단하는 곳(선문자/안받음문자/티엠예약
        # 중복 방지)이 있어 RESULT 코드/EVENT_TYPE 값을 그 값으로 매핑해서 실어줌. TM_LOGS
        # 쪽은 코드화됐지만 SARANG_ACTIVITY_LOGS.EVENT_TYPE은 아직 한글 그대로임(이번 범위 밖).
        LOG_CATEGORY = {'RESERVED_TM': 'tmReserved', '선문자발송': 'welcomeMsg', '부재중문자발송': 'noAnswerMsg'}
        # source: 실제 통화 시도(call)인지, 문자 발송 같은 비통화 이벤트(activity)인지 구분 —
        # 문자만 보낸 건 통화를 시도한 게 아니라서 기존 예약을 무효화하면 안 됨(프론트에서 사용).
        for r in call_rows:
            timeline_by_id[r['sarang_id']].append(
                {'id': r['log_id'], 'label': r['label'], 'category': LOG_CATEGORY.get(r['result']), 'source': 'call',
                 'actorName': r['actor_name'], 'createdAt': r['created_at']}
            )
        for r in activity_rows:
            timeline_by_id[r['sarang_id']].append(
                {'id': r['log_id'], 'label': r['label'], 'category': LOG_CATEGORY.get(r['label']), 'source': 'activity',
                 'actorName': r['actor_name'], 'createdAt': r['created_at']}
            )
        for sid in timeline_by_id:
            timeline_by_id[sid].sort(key=lambda x: x['createdAt'], reverse=True)

    # IS_DROPPED 컬럼을 없애고 tm_logs 기준으로 판단하기로 함 — 별도 상태
    # 저장 없이, 가장 최근 통화 결과가 거절/비합/무효면 중단된 것으로 취급.
    DROPPED_RESULTS = {'REJECT', 'UNFIT', 'INVALID'}
    latest_call_by_id = {}
    no_answer_count_by_id = {}
    for r in call_rows:
        prev = latest_call_by_id.get(r['sarang_id'])
        if not prev or r['created_at'] > prev['created_at']:
            latest_call_by_id[r['sarang_id']] = r
        if r['result'] == 'NO_ANSWER':
            no_answer_count_by_id[r['sarang_id']] = no_answer_count_by_id.get(r['sarang_id'], 0) + 1

    list_ = []
    for r in rows:
        latest_call = latest_call_by_id.get(r['sarang_id'])
        is_dropped = bool(latest_call) and latest_call['result'] in DROPPED_RESULTS
        list_.append({
            'sarangId': r['sarang_id'],
            'name': r['name'],
            'phone': r['phone'],
            'age': r['age'],
            'mbti': r['mbti'],
            'residenceStation': r['residence_station'],
            'stage': r['stage'],
            'currentProcess': r['current_process'],
            'isDropped': is_dropped,
            'droppedReason': latest_call['label'] if is_dropped else None,
            'recruitmentType': r['recruitment_type'],
            'inflowDate': r['inflow_date'],
            'createdAt': r['created_at'],
            'inflowMemberName': r['inflow_member_name'],
            'team': r['team'],
            'noAnswerCount': no_answer_count_by_id.get(r['sarang_id'], 0),
            'inflowDetails': {
                'regionName': r['region_name'],
                'reaction': r['reaction'],
                'location': r['location'],
                'env': r['env'],
                'introducerName': r['introducer_name'],
                'helperNames': _helper_names(r['helper_member_ids']),
                'tmReservedAt': r['tm_reserved_at'],
            },
            'habJaeYang': {
                'guideName': r['guide_name'],
                'callerName': r['caller_name'],
                'teacherName': r['teacher_name'],
            } if r['hab_jae_yang_id'] else None,
            'timeline': timeline_by_id.get(r['sarang_id'], []),
        })

    return JsonResponse({'success': True, 'list': list_})


@csrf_exempt
@require_jwt
def run_shed_gacha(request, *args, **kwargs):
    """선한 양치기 인도권 가챠 — 합재양 저장 직후 자동 호출됨. 최소 버전: 확률 없이
    항상 티엠자가 인도자로 확정(원래는 회차별 60/70/100% 확률로 유입자 vs 티엠자 결정
    — GACHA_COUNTS 테이블 포함해서 나중에 추가)."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    sarang_id = str(body.get('docId') or '').strip()
    inflow_name = str(body.get('inflowName') or '').strip()
    tm_name = str(body.get('tmName') or '').strip()
    if not sarang_id or not inflow_name or not tm_name:
        return JsonResponse({'success': False, 'message': '필수 값 누락'}, status=400)

    client = DataRouterClient()
    winner_id = _member_id_by_name(client, tm_name)
    if not winner_id:
        return JsonResponse({'success': False, 'message': f'티엠자 이름[{tm_name}]이 명단에 없어!'}, status=400)

    affected = client.exec(
        "UPDATE SARANG_HAB_JAE_YANG SET GUIDE_MEMBER_ID = :1 WHERE SARANG_ID = :2 AND IS_ACTIVE = 1",
        [winner_id, sarang_id],
    )
    if not affected:
        return JsonResponse({'success': False, 'message': '합재양을 먼저 저장해줘'}, status=400)

    return JsonResponse({
        'success': True, 'winner': 'tm', 'winnerName': tm_name,
        'inflowName': inflow_name, 'tmName': tm_name,
        'currentRound': 1, 'nextProb': 100,
    })


@csrf_exempt
@require_jwt
def cancel_shed_habjaeyang(request, *args, **kwargs):
    """합재양 제출 취소 — services/main/src/routes/assets.js 포팅(텔레그램 메시지 삭제·
    매칭전광판 갱신은 이 프로젝트에 아직 없는 기능이라 제외). 만남픽스 통화 로그와
    합재양작성 활동 로그를 지우고 합재양은 하드 삭제 대신 IS_ACTIVE=0으로 비활성화한 뒤
    STAGE를 '티엠'으로 되돌림 — delete_log가 MEET_FIX 로그 하나 지울 때의 원복 규칙과 동일."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    sarang_id = str(body.get('docId') or '').strip()
    if not sarang_id:
        return JsonResponse({'success': False, 'message': '필수 값 누락'}, status=400)

    client = DataRouterClient()
    hj = client.query_one(
        "SELECT HAB_JAE_YANG_ID FROM SARANG_HAB_JAE_YANG WHERE SARANG_ID = :1 AND IS_ACTIVE = 1",
        [sarang_id],
    )
    if not hj:
        return JsonResponse({'success': False, 'message': '취소할 합재양을 찾을 수 없어요'}, status=404)

    meet_fix_log = client.query_one(
        "SELECT TM_ID FROM TM_LOGS WHERE SARANG_ID = :1 AND RESULT = 'MEET_FIX' ORDER BY CREATED_AT DESC FETCH FIRST 1 ROWS ONLY",
        [sarang_id],
    )
    activity_log = client.query_one(
        "SELECT ACTIVITY_ID FROM SARANG_ACTIVITY_LOGS WHERE SARANG_ID = :1 AND EVENT_TYPE = '합재양작성' ORDER BY CREATED_AT DESC FETCH FIRST 1 ROWS ONLY",
        [sarang_id],
    )

    stmts = [{'sql': "UPDATE SARANG_HAB_JAE_YANG SET IS_ACTIVE = 0 WHERE HAB_JAE_YANG_ID = :1", 'args': [hj['hab_jae_yang_id']]}]
    if meet_fix_log:
        stmts.append({'sql': "DELETE FROM TM_LOGS WHERE TM_ID = :1", 'args': [meet_fix_log['tm_id']]})
    if activity_log:
        stmts.append({'sql': "DELETE FROM SARANG_ACTIVITY_LOGS WHERE ACTIVITY_ID = :1", 'args': [activity_log['activity_id']]})
    stmts.append({'sql': "UPDATE SARANG SET STAGE = '티엠' WHERE SARANG_ID = :1", 'args': [sarang_id]})
    client.tx(stmts)

    return JsonResponse({'success': True})


@csrf_exempt
def shed_reject(request, *args, **kwargs):
    # TODO: services/main/src/routes/assets.js 의 POST /shed-reject 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/assets.js"}, status=501)


@csrf_exempt
def shed_revive(request, *args, **kwargs):
    # TODO: services/main/src/routes/assets.js 의 POST /shed-revive 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/assets.js"}, status=501)


@csrf_exempt
@require_jwt
def shed_lookup_teams(request, *args, **kwargs):
    """유입자 이름 목록 → 그 사람의 현재 소속팀(REGION_CODE) 맵. shed 링크 번호(SOURCE_LINK)는
    신청 당시 고정값이라, 실제 유입자가 다른 팀 소속이면 그 팀으로 이관되도록 프론트에서
    이 값을 링크 번호보다 우선해서 씀."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    names = [str(n).strip() for n in (body.get('names') or []) if isinstance(n, str) and str(n).strip()][:200]
    if not names:
        return JsonResponse({'ok': True, 'teams': {}})

    placeholders = ', '.join(f':{i + 1}' for i in range(len(names)))
    rows = DataRouterClient().query(
        f"""SELECT m.NAME, mah.REGION_CODE AS TEAM
              FROM MEMBERS m
              JOIN MEMBER_AFFILIATION_HISTORIES mah ON mah.MEMBER_ID = m.MEMBER_ID AND mah.IS_CURRENT = 1
             WHERE m.NAME IN ({placeholders}) AND m.DELETED_AT IS NULL""",
        names,
    )
    teams = {}
    for r in rows:
        if r['team'] and r['name'] not in teams:
            teams[r['name']] = r['team']
    return JsonResponse({'ok': True, 'teams': teams})


@csrf_exempt
@require_jwt
def shed_pending_reject(request, *args, **kwargs):
    """SARANG_INTAKE_QUEUE 반려 처리 — SARANG 행은 만들지 않고 상태만 rejected로."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    intake_id = str(body.get('intakeId') or '').strip()
    if not intake_id:
        return JsonResponse({'success': False, 'message': 'intakeId 필요'}, status=400)

    client = DataRouterClient()
    intake = client.query_one("SELECT STATUS FROM SARANG_INTAKE_QUEUE WHERE INTAKE_ID = :1", [intake_id])
    if not intake:
        return JsonResponse({'success': False, 'message': '대기열 항목을 찾을 수 없습니다'}, status=404)
    if intake['status'] != 'submitted':
        return JsonResponse({'success': False, 'message': f"아직 이관 요청되지 않았거나 이미 처리된 항목입니다({intake['status']})"}, status=400)

    client.exec(
        """UPDATE SARANG_INTAKE_QUEUE SET STATUS = 'rejected', REVIEWED_BY_MEMBER_ID = :1, REVIEWED_AT = SYSTIMESTAMP
           WHERE INTAKE_ID = :2""",
        [request.user['sabun'], intake_id],
    )
    return JsonResponse({'success': True})


@csrf_exempt
def shed_webhook(request, *args, **kwargs):
    """shed 프로젝트(Google Apps Script 경유)가 호출.
    - 최초 신청(name/phone 포함): SARANG_INTAKE_QUEUE에 pending으로 적재.
    - {type:'update', rowNum}: shed 관리자의 "이관하기" — pending을 submitted로
      전환만 함(Ddochi 담당자의 이관받기/반려하기를 건너뛰지 않도록, SARANG은
      아직 안 만듦)."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    shed_key = settings.SHED_INTERNAL_KEY
    if not shed_key or request.headers.get('X-Shed-Key') != shed_key:
        return JsonResponse({'ok': False}, status=401)

    body = _json_body(request)

    if body.get('type') == 'update':
        intake_id = str(body.get('rowNum') or '').strip()
        if not intake_id:
            return JsonResponse({'ok': False, 'message': 'rowNum 필요'}, status=400)
        env = str(body.get('env') or '').strip() or None
        reaction = str(body.get('reaction') or '').strip() or None
        tm_location = str(body.get('tmLocation') or '').strip() or None
        tm_datetime = str(body.get('tmDatetime') or '').strip() or None

        client = DataRouterClient()

        def _resolve_member_id(sabun, name):
            # shed가 사번을 같이 보내면 그대로 쓰고(신규), 없거나 재이관 시 placeholder인
            # 'existing'이면 이름으로 MEMBERS를 조회해서 구함(구버전 shed 호환 겸용).
            sabun = str(sabun or '').strip()
            if sabun and sabun != 'existing':
                return sabun
            name = str(name or '').strip()
            if not name:
                return None
            row = client.query_one(
                "SELECT MEMBER_ID FROM MEMBERS WHERE NAME = :1 AND DELETED_AT IS NULL FETCH FIRST 1 ROWS ONLY",
                [name],
            )
            return row['member_id'] if row else None

        # 유입자/조력자 — 이름 텍스트는 저장 안 하고 MEMBERS.MEMBER_ID만 저장(표시할 땐
        # 조회 시 MEMBERS 조인). 유입자 추첨(2명 이상 후보)에서 낙첨된 사람들이 조력자.
        introducer_id = _resolve_member_id(body.get('introducerSabun'), body.get('introducer'))
        helper_names = body.get('helperNames') or []
        helper_sabuns = body.get('helperSabuns') or []
        helper_ids = []
        for i, name in enumerate(helper_names):
            mid = _resolve_member_id(helper_sabuns[i] if i < len(helper_sabuns) else None, name)
            if mid:
                helper_ids.append(mid)
        helper_ids_str = ', '.join(helper_ids) or None

        affected = client.exec(
            """UPDATE SARANG_INTAKE_QUEUE
                  SET STATUS = 'submitted', ENV = :1, REACTION = :2, INTRODUCER_MEMBER_ID = :3, LOCATION = :4,
                      HELPER_MEMBER_IDS = :5,
                      TM_RESERVED_AT = CASE WHEN :6 IS NOT NULL THEN TO_TIMESTAMP(:7, 'YYYY-MM-DD"T"HH24:MI') END
                WHERE INTAKE_ID = :8 AND STATUS = 'pending'""",
            [env, reaction, introducer_id, tm_location, helper_ids_str, tm_datetime, tm_datetime, intake_id],
        )
        if not affected:
            return JsonResponse({'ok': False, 'message': '대상을 찾을 수 없거나 이미 처리됨'}, status=400)
        return JsonResponse({'ok': True})

    name = str(body.get('name') or '').strip()
    phone_raw = re.sub(r'\s', '', str(body.get('phone') or ''))
    phone_normalized = re.sub(r'[^0-9]', '', phone_raw)
    age = body.get('age')
    try:
        age = int(age) if age else None
    except (TypeError, ValueError):
        age = None
    event = str(body.get('event') or '').strip()
    region = str(body.get('region') or '').strip() or None
    reaction = str(body.get('reaction') or '').strip() or None
    tm_location = str(body.get('tmLocation') or '').strip() or None
    tm_datetime = str(body.get('tmDatetime') or '').strip() or None
    rest_type = str(body.get('rest') or '').strip() or None
    mbti = str(body.get('mbti') or '').strip() or None

    if not name or len(phone_normalized) < 10:
        return JsonResponse({'ok': False, 'message': '이름/전화번호 필요'}, status=400)
    if event not in ['1', '2', '3', '4', '5', '6']:
        return JsonResponse({'ok': False, 'message': '링크 번호 오류'}, status=400)

    client = DataRouterClient()
    existing = client.query_one(
        "SELECT INTAKE_ID FROM SARANG_INTAKE_QUEUE WHERE PHONE_NORMALIZED = :1 AND STATUS = 'pending' "
        "FETCH FIRST 1 ROWS ONLY",
        [phone_normalized],
    )
    if existing:
        return JsonResponse({'ok': True, 'skipped': True})

    intake_id = uuid.uuid4().hex.upper()
    client.exec(
        """INSERT INTO SARANG_INTAKE_QUEUE
             (INTAKE_ID, NAME, PHONE, PHONE_NORMALIZED, AGE, MBTI, SOURCE_LINK,
              REGION_NAME, REACTION, LOCATION, REST_TYPE, TM_RESERVED_AT)
           VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9, :10, :11,
                   CASE WHEN :12 IS NOT NULL THEN TO_TIMESTAMP(:12, 'YYYY-MM-DD"T"HH24:MI') END)""",
        [intake_id, name, phone_raw, phone_normalized, age, mbti, int(event),
         region, reaction, tm_location, rest_type, tm_datetime],
    )
    return JsonResponse({'ok': True, 'skipped': False, 'intakeId': intake_id})


@csrf_exempt
@require_jwt
def shed_pending_list(request, *args, **kwargs):
    """SARANG_INTAKE_QUEUE의 submitted(shed 관리자가 이관하기 클릭한) 항목 목록 —
    Ddochi 담당자의 이관받기/반려하기 대상."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    client = DataRouterClient()
    rows = client.query(
        """SELECT q.INTAKE_ID, q.NAME, q.PHONE, q.AGE, q.MBTI, q.SOURCE_LINK, q.REGION_NAME, q.REACTION,
                  q.LOCATION, q.ENV, im.NAME AS INTRODUCER_NAME, q.HELPER_MEMBER_IDS, q.TM_RESERVED_AT, q.CREATED_AT
             FROM SARANG_INTAKE_QUEUE q
             LEFT JOIN MEMBERS im ON im.MEMBER_ID = q.INTRODUCER_MEMBER_ID
            WHERE q.STATUS = 'submitted'
            ORDER BY q.CREATED_AT ASC"""
    )
    _helper_names = _helper_names_resolver(client, rows)
    list_ = [{
        'intakeId': r['intake_id'], 'name': r['name'], 'phone': r['phone'], 'age': r['age'],
        'mbti': r['mbti'], 'sourceLink': r['source_link'], 'regionName': r['region_name'], 'reaction': r['reaction'],
        'location': r['location'], 'env': r['env'], 'introducerName': r['introducer_name'],
        'helperNames': _helper_names(r['helper_member_ids']),
        'tmReservedAt': r['tm_reserved_at'], 'createdAt': r['created_at'],
    } for r in rows]
    return JsonResponse({'success': True, 'list': list_})


@csrf_exempt
@require_jwt
def shed_pending_rejected_list(request, *args, **kwargs):
    """SARANG_INTAKE_QUEUE의 rejected 항목 목록 — 회생하기(되살리기) 대상."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    client = DataRouterClient()
    rows = client.query(
        """SELECT q.INTAKE_ID, q.NAME, q.PHONE, q.AGE, q.MBTI, q.SOURCE_LINK, q.REGION_NAME, q.REACTION,
                  q.LOCATION, q.ENV, im.NAME AS INTRODUCER_NAME, q.HELPER_MEMBER_IDS, q.TM_RESERVED_AT, q.CREATED_AT
             FROM SARANG_INTAKE_QUEUE q
             LEFT JOIN MEMBERS im ON im.MEMBER_ID = q.INTRODUCER_MEMBER_ID
            WHERE q.STATUS = 'rejected'
            ORDER BY q.REVIEWED_AT DESC"""
    )
    _helper_names = _helper_names_resolver(client, rows)
    list_ = [{
        'intakeId': r['intake_id'], 'name': r['name'], 'phone': r['phone'], 'age': r['age'],
        'mbti': r['mbti'], 'sourceLink': r['source_link'], 'regionName': r['region_name'], 'reaction': r['reaction'],
        'location': r['location'], 'env': r['env'], 'introducerName': r['introducer_name'],
        'helperNames': _helper_names(r['helper_member_ids']),
        'tmReservedAt': r['tm_reserved_at'], 'createdAt': r['created_at'],
    } for r in rows]
    return JsonResponse({'success': True, 'list': list_})


@csrf_exempt
@require_jwt
def shed_pending_revive(request, *args, **kwargs):
    """반려된(rejected) 큐 항목을 되살려 submitted로 되돌림 — 이관받기 목록에 재등장."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    intake_id = str(body.get('intakeId') or '').strip()
    if not intake_id:
        return JsonResponse({'success': False, 'message': 'intakeId 필요'}, status=400)

    affected = DataRouterClient().exec(
        "UPDATE SARANG_INTAKE_QUEUE SET STATUS = 'submitted' WHERE INTAKE_ID = :1 AND STATUS = 'rejected'",
        [intake_id],
    )
    if not affected:
        return JsonResponse({'success': False, 'message': '반려 상태인 건을 찾을 수 없어요'}, status=400)
    return JsonResponse({'success': True})

