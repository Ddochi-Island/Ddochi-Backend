"""assets.js 포팅 대상 — assets 라우트 스텁 (구조만, 로직은 미구현)."""
import hashlib
import json
import re
import time
import uuid

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from api.auth.gate import get_author_context, require_jwt
from api.clients.data_router import DataRouterClient


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


@csrf_exempt
def get_assets(request, *args, **kwargs):
    # TODO: services/main/src/routes/assets.js 의 POST /get-assets 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/assets.js"}, status=501)


@csrf_exempt
def get_matching_history(request, *args, **kwargs):
    # TODO: services/main/src/routes/assets.js 의 POST /get-matching-history 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/assets.js"}, status=501)


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


@csrf_exempt
def update_match(request, *args, **kwargs):
    # TODO: services/main/src/routes/assets.js 의 POST /update-match 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/assets.js"}, status=501)


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
                                 HAS_CENTER_ENV = :22, IS_TAKING_MEDS = :23, HAS_MENTAL_ILLNESS = :24
                           WHERE HAB_JAE_YANG_ID = :25""",
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
                             HAS_CENTER_ENV, IS_TAKING_MEDS, HAS_MENTAL_ILLNESS)
                          VALUES (:1, :2, :3, :4, :5, :6, :7,
                                  CASE WHEN :8 IS NOT NULL THEN TO_TIMESTAMP(:9, 'YYYY-MM-DD"T"HH24:MI') END, :10,
                                  :11, :12, :13, :14,
                                  :15, :16, :17, :18,
                                  :19, :20, :21, :22, :23,
                                  :24, :25, :26)""",
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
        client.tx(stmts)
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
    else:
        affected = client.exec(
            "DELETE FROM SARANG_ACTIVITY_LOGS WHERE ACTIVITY_ID = :1 AND SARANG_ID = :2", [log_id, sarang_id]
        )
        if not affected:
            return JsonResponse({'success': False, 'message': '로그를 찾을 수 없어요'}, status=404)

    return JsonResponse({'success': True})


@csrf_exempt
def toggle_hj_status(request, *args, **kwargs):
    # TODO: services/main/src/routes/assets.js 의 POST /toggle-hj-status 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/assets.js"}, status=501)


@csrf_exempt
def edit_match(request, *args, **kwargs):
    # TODO: services/main/src/routes/assets.js 의 POST /edit-match 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/assets.js"}, status=501)


@csrf_exempt
def update_approval(request, *args, **kwargs):
    # TODO: services/main/src/routes/assets.js 의 POST /update-approval 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/assets.js"}, status=501)


@csrf_exempt
def postpone_meeting(request, *args, **kwargs):
    # TODO: services/main/src/routes/assets.js 의 POST /postpone-meeting 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/assets.js"}, status=501)


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
def submit_habjaeyang_new(request, *args, **kwargs):
    # TODO: services/main/src/routes/assets.js 의 POST /submit-habjaeyang-new 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/assets.js"}, status=501)


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
                    (SARANG_ID, REGION_NAME, REACTION, LOCATION, ENV, INTRODUCER_MEMBER_ID, HELPER_MEMBER_IDS, TM_RESERVED_AT)
                  SELECT :1, REGION_NAME, REACTION, LOCATION, ENV, INTRODUCER_MEMBER_ID, HELPER_MEMBER_IDS, TM_RESERVED_AT
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
    반환하면서 각 항목에 team을 실어준다."""
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
             LEFT JOIN SARANG_INFLOW_DETAILS sid ON sid.SARANG_ID = s.SARANG_ID
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

