# tel_router_py가 HMAC 검증을 마친 인라인 버튼 callback_query를 위임하는 창구.
# services/main/src/routes/internalTelegram.js 포팅 — 'hj'(합재양 답장/창개설/재가) 액션만
# 지원(chk/wakeup은 이 프로젝트에 해당 기능이 아직 없어 범위 밖).
import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from api.clients.data_router import DataRouterClient
from api.telegram.habjaeyang import refresh_hj_markup
from api.telegram.internal_auth import check_internal_auth
from api.telegram.matching_dashboard import refresh_matching_dashboard_for_sarang
from api.views.assets import _set_habjaeyang_approval, _toggle_hj_field

HJ_SHORT = {'r': 'reply', 'w': 'window', 'a': 'approve', 'n': 'noop'}


def _json_body(request):
    try:
        return json.loads(request.body or b'{}')
    except (TypeError, ValueError):
        return {}


def _resolve_actor(client, telegram_id, sarang_id):
    """SARANG_ACTIVITY_LOGS.ACTOR_MEMBER_ID는 NOT NULL FK라 실제 MEMBER_ID가 있어야 함.
    누른 사람이 MEMBERS.TELEGRAM_ID로 연결돼 있으면 그 사람, 아니면 이 사랑이의
    유입담당자(INFLOW_MEMBER_ID)로 대체 — legacy의 sabun||'cron' 폴백과 같은 역할이지만
    이 스키마엔 'cron' 같은 시스템 계정이 없어서 실존 회원으로 대체."""
    if telegram_id:
        row = client.query_one("SELECT MEMBER_ID FROM MEMBERS WHERE TELEGRAM_ID = :1", [telegram_id])
        if row:
            return row['member_id']
    row = client.query_one("SELECT INFLOW_MEMBER_ID FROM SARANG WHERE SARANG_ID = :1", [sarang_id])
    return row['inflow_member_id'] if row else None


def _handle_hj(client, args, chat_id, message_id, telegram_id):
    sarang_id, _, code = str(args or '').rpartition('.')
    action = HJ_SHORT.get(code, code)
    if not sarang_id:
        return {'toast': '⚠️'}

    if action == 'noop':
        return {'toast': '🦔'}

    if action in ('reply', 'window'):
        col = 'HAS_REPLIED' if action == 'reply' else 'IS_WINDOW_OPENED'
        new_val = _toggle_hj_field(client, sarang_id, col)
        if new_val is None:
            return {'toast': '⚠️ 합재양 없음'}
        refresh_hj_markup(client, sarang_id, chat_id, message_id)
        if action == 'reply':
            toast = '✅ 답장 표시' if new_val else '⏪ 답장 해제'
        else:
            toast = '✅ 창 개설' if new_val else '⏪ 창 해제'
        return {'toast': toast}

    if action == 'approve':
        actor = _resolve_actor(client, telegram_id, sarang_id)
        if not actor:
            return {'toast': '⚠️ 처리 실패'}
        if _set_habjaeyang_approval(client, sarang_id, actor, 'approved') is None:
            return {'toast': '⚠️ 합재양 없음'}
        refresh_hj_markup(client, sarang_id, chat_id, message_id)
        try:
            refresh_matching_dashboard_for_sarang(client, sarang_id)
        except Exception:
            logging.getLogger('api.views.internal_telegram').warning(
                '[handle_hj:approve] matching dashboard refresh failed', exc_info=True,
            )
        return {'toast': '🎉 재가 완료!'}

    return {'toast': '⚠️ 알 수 없는 동작'}


@csrf_exempt
def telegram_callback(request, *args, **kwargs):
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    if not check_internal_auth(request):
        return JsonResponse({'error': 'unauthorized'}, status=401)

    body = _json_body(request)
    action = str(body.get('action') or '')
    args_str = str(body.get('args') or '')
    chat_id = body.get('chatId')
    message_id = body.get('messageId')
    telegram_id = str(body.get('fromId') or '').strip() or None

    if action != 'hj':
        return JsonResponse({'toast': None})

    client = DataRouterClient()
    result = _handle_hj(client, args_str, chat_id, message_id, telegram_id)
    return JsonResponse(result)
