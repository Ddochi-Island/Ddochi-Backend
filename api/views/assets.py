"""assets.js 포팅 대상 — assets 라우트 스텁 (구조만, 로직은 미구현)."""
import json
import time

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from api.auth.gate import get_author_context, require_jwt
from api.clients.data_router import DataRouterClient


def _json_body(request):
    try:
        return json.loads(request.body or b'{}')
    except (TypeError, ValueError):
        return {}


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
def submit_result(request, *args, **kwargs):
    # TODO: services/main/src/routes/assets.js 의 POST /submit-result 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/assets.js"}, status=501)


@csrf_exempt
def delete_log(request, *args, **kwargs):
    # TODO: services/main/src/routes/assets.js 의 POST /delete-log 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/assets.js"}, status=501)


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
def shed_register(request, *args, **kwargs):
    # TODO: services/main/src/routes/assets.js 의 POST /shed-register 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/assets.js"}, status=501)


@csrf_exempt
def shed_reject_duplicate(request, *args, **kwargs):
    # TODO: services/main/src/routes/assets.js 의 POST /shed-reject-duplicate 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/assets.js"}, status=501)


@csrf_exempt
def get_shed_prospects(request, *args, **kwargs):
    # TODO: services/main/src/routes/assets.js 의 POST /get-shed-prospects 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/assets.js"}, status=501)


@csrf_exempt
def run_shed_gacha(request, *args, **kwargs):
    # TODO: services/main/src/routes/assets.js 의 POST /run-shed-gacha 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/assets.js"}, status=501)


@csrf_exempt
def cancel_shed_habjaeyang(request, *args, **kwargs):
    # TODO: services/main/src/routes/assets.js 의 POST /cancel-shed-habjaeyang 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/assets.js"}, status=501)


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
def shed_lookup_teams(request, *args, **kwargs):
    # TODO: services/main/src/routes/assets.js 의 POST /shed/lookup-teams 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/assets.js"}, status=501)


@csrf_exempt
def shed_pending_reject(request, *args, **kwargs):
    # TODO: services/main/src/routes/assets.js 의 POST /shed-pending-reject 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/assets.js"}, status=501)


@csrf_exempt
def shed_webhook(request, *args, **kwargs):
    # TODO: services/main/src/routes/assets.js 의 POST /shed-webhook 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/assets.js"}, status=501)


@csrf_exempt
def shed_pending_list(request, *args, **kwargs):
    # TODO: services/main/src/routes/assets.js 의 POST /shed/pending-list 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/assets.js"}, status=501)

