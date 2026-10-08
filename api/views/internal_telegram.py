# tel_router_py가 HMAC 검증을 마친 인라인 버튼 callback_query를 위임하는 창구.
# services/main/src/routes/internalTelegram.js 포팅 — 'hj'(합재양 답장/창개설/재가) 액션만
# 지원(chk/wakeup은 이 프로젝트에 해당 기능이 아직 없어 범위 밖).
import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from api.clients.data_router import DataRouterClient
from api.telegram.habjaeyang import HJ_REJECT_REASONS, refresh_hj_markup, refresh_hj_reason_markup
from api.telegram.internal_auth import check_internal_auth
from api.telegram.matching_dashboard import refresh_matching_dashboard_for_sarang
from api.telegram import match_result_input
from api.telegram.name_lookup import find_open_matches
from api.telegram.shed_union_dashboards import refresh_shed_tm, refresh_shed_unified, shed_groups_for_sarang
from api.telegram.team_stats import refresh_team_stats_for_sarang
from api.views.assets import _member_id_by_name, _set_habjaeyang_approval, _toggle_hj_field

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
    if not sarang_id:
        return {'toast': '⚠️'}

    if code == 'x':
        refresh_hj_reason_markup(client, sarang_id, chat_id, message_id)
        return {'toast': '사유를 선택해줘'}

    if code == 'b':
        refresh_hj_markup(client, sarang_id, chat_id, message_id)
        return {'toast': None}

    if code[:1] == 'x' and code[1:].isdigit():
        reason_idx = int(code[1:])
        if not (1 <= reason_idx <= len(HJ_REJECT_REASONS)):
            return {'toast': '⚠️ 알 수 없는 사유'}
        reason = HJ_REJECT_REASONS[reason_idx - 1]
        actor = _resolve_actor(client, telegram_id, sarang_id)
        if not actor:
            return {'toast': '⚠️ 처리 실패'}
        result = _set_habjaeyang_approval(client, sarang_id, actor, 'rejected', reason=reason)
        if result is None:
            return {'toast': '⚠️ 합재양 없음'}
        refresh_hj_markup(client, sarang_id, chat_id, message_id)
        for group in shed_groups_for_sarang(client, sarang_id):
            try:
                refresh_shed_unified(client, group)
            except Exception:
                logging.getLogger('api.views.internal_telegram').warning(
                    '[handle_hj:reject] shed unified dashboard refresh failed', exc_info=True,
                )
        return {'toast': f'🚫 반려 처리 완료 ({reason})'}

    action = HJ_SHORT.get(code, code)

    if action == 'noop':
        return {'toast': '🦔'}

    if action in ('reply', 'window'):
        col = 'HAS_REPLIED' if action == 'reply' else 'IS_WINDOW_OPENED'
        new_val = _toggle_hj_field(client, sarang_id, col)
        if new_val is None:
            return {'toast': '⚠️ 합재양 없음'}
        refresh_hj_markup(client, sarang_id, chat_id, message_id)
        for group in shed_groups_for_sarang(client, sarang_id):
            try:
                refresh_shed_unified(client, group)
            except Exception:
                logging.getLogger('api.views.internal_telegram').warning(
                    '[handle_hj:%s] shed unified dashboard refresh failed', action, exc_info=True,
                )
        if action == 'reply':
            toast = '✅ 답장 표시' if new_val else '⏪ 답장 해제'
        else:
            toast = '✅ 창 개설' if new_val else '⏪ 창 해제'
        return {'toast': toast}

    if action == 'approve':
        actor = _resolve_actor(client, telegram_id, sarang_id)
        if not actor:
            return {'toast': '⚠️ 처리 실패'}
        result = _set_habjaeyang_approval(client, sarang_id, actor, 'approved')
        if result is None:
            return {'toast': '⚠️ 합재양 없음'}
        if result.get('blocked'):
            return {'toast': '⚠️ 답장/창개설 먼저 해줘'}
        refresh_hj_markup(client, sarang_id, chat_id, message_id)
        try:
            refresh_matching_dashboard_for_sarang(client, sarang_id)
        except Exception:
            logging.getLogger('api.views.internal_telegram').warning(
                '[handle_hj:approve] matching dashboard refresh failed', exc_info=True,
            )
        try:
            refresh_team_stats_for_sarang(client, sarang_id)
        except Exception:
            logging.getLogger('api.views.internal_telegram').warning(
                '[handle_hj:approve] team stats refresh failed', exc_info=True,
            )
        for group in shed_groups_for_sarang(client, sarang_id):
            try:
                refresh_shed_unified(client, group)
                refresh_shed_tm(client, group)
            except Exception:
                logging.getLogger('api.views.internal_telegram').warning(
                    '[handle_hj:approve] shed dashboard refresh failed', exc_info=True,
                )
        return {'toast': '🎉 재가 완료!'}

    return {'toast': '⚠️ 알 수 없는 동작'}


def _assign_teacher(client, short_code, raw_teacher):
    # 매칭현황판 각 행의 '/t_<sarang_id 뒤 8자리>' 탭형 명령 처리 — edit_match(웹, type=teacher)의
    # 이름 파싱 규칙과 동일하게 맞춤(assets.py:821). 8자리만 씀 — 32자 전체는 텔레그램의
    # bot_command 엔티티 인식 길이 한도(32자)를 넘어서 탭이 안 먹힘.
    row = client.query_one(
        """SELECT s.SARANG_ID, spi.NAME, hj.HAB_JAE_YANG_ID
             FROM SARANG s
             JOIN SARANG_PERSONAL_INFO spi ON spi.PERSONAL_INFO_ID = s.PERSONAL_INFO_ID
             JOIN SARANG_HAB_JAE_YANG hj   ON hj.SARANG_ID = s.SARANG_ID AND hj.IS_ACTIVE = 1
            WHERE UPPER(SUBSTR(s.SARANG_ID, -8)) = UPPER(:1)
              AND s.DELETED_AT IS NULL""",
        [short_code],
    )
    if not row:
        return {'ok': False, 'message': '⚠️ 대상을 찾을 수 없어(이미 지나갔거나 잘못된 링크일 수 있어)'}

    raw = str(raw_teacher or '').strip()
    is_other_region = raw.endswith('(타지역)')
    teacher_name = raw[:-5].strip() if is_other_region else raw.split('(')[0].strip()
    if not teacher_name:
        return {'ok': False, 'message': '⚠️ 교사 이름이 비어있어'}

    teacher_id, override = None, None
    if teacher_name == '-':  # 교사 배정 해제 — 웹 edit_match(type=teacher)와 같은 규칙
        done = f"✅ {row['name']} — 교사 배정을 해제했어!"
    elif is_other_region:
        override = raw
        done = f"✅ {row['name']} — 교사 [{teacher_name}] 입력 완료!"
    else:
        teacher_id = _member_id_by_name(client, teacher_name)
        if not teacher_id:
            return {'ok': False, 'message': f'⚠️ [{teacher_name}] 명단에 없어! 타지역이면 뒤에 "(타지역)"을 붙여줘'}
        done = f"✅ {row['name']} — 교사 [{teacher_name}] 입력 완료!"

    client.exec(
        "UPDATE SARANG_HAB_JAE_YANG SET TEACHER_MEMBER_ID = :1, TEACHER_NAME_OVERRIDE = :2 WHERE HAB_JAE_YANG_ID = :3",
        [teacher_id, override, row['hab_jae_yang_id']],
    )
    try:
        refresh_matching_dashboard_for_sarang(client, row['sarang_id'])
    except Exception:
        logging.getLogger('api.views.internal_telegram').warning(
            '[assign_teacher] matching dashboard refresh failed', exc_info=True,
        )
    return {'ok': True, 'message': done}


@csrf_exempt
def telegram_teacher_assign(request, *args, **kwargs):
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    if not check_internal_auth(request):
        return JsonResponse({'error': 'unauthorized'}, status=401)

    body = _json_body(request)
    short_code = str(body.get('shortCode') or '').strip()
    teacher_name = str(body.get('teacherName') or '')
    client = DataRouterClient()
    name = str(body.get('name') or '').strip()
    if name and not short_code:  # "/t 섭외자 교사" — 이름으로 그 방 지역의 매칭 건 찾기
        found = find_open_matches(client, name, body.get('chatId'))
        if not found:
            return JsonResponse({'ok': False, 'message': f'⚠️ [{name}] 진행 중인 매칭을 이 지역에서 못 찾았어'})
        if len(found) > 1:
            return JsonResponse({'ok': False, 'message': _pick_message(name, found, 't', teacher_name)})
        short_code = found[0]['short']
    if not short_code:
        return JsonResponse({'ok': False, 'message': '⚠️ 잘못된 요청'})

    result = _assign_teacher(client, short_code, teacher_name)
    return JsonResponse(result)


def _pick_message(name, found, cmd, teacher_name=''):
    """같은 이름이 여러 명 — 날짜/인도자와 함께 그 건의 코드 명령을 보여줌. 결과(/r_)는 탭하면 바로 실행되고,
    교사(/t_)는 교사 이름까지 붙인 명령을 복사해서 보내게 <code>로."""
    lines = [f'⚠️ [{name}]이(가) {len(found)}명이야. 아래에서 골라줘']
    for f in found:
        command = f"/{cmd}_{f['short'].lower()}"
        shown = f'<code>{command} {teacher_name}</code>' if cmd == 't' else command
        lines.append(f"· {f['mt']} 인도자 {f['guide']} → {shown}")
    return '\n'.join(lines)


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

    client = DataRouterClient()
    if action == match_result_input.ACTION:  # 매칭 결과 버튼(/r_)
        return JsonResponse(match_result_input.handle_callback(
            client, args_str, chat_id, message_id, lambda c, sid: _resolve_actor(c, telegram_id, sid)))
    if action != 'hj':
        return JsonResponse({'toast': None})

    result = _handle_hj(client, args_str, chat_id, message_id, telegram_id)
    return JsonResponse(result)


@csrf_exempt
def telegram_match_result(request, *args, **kwargs):
    """tel_router가 넘기는 매칭 결과 입력 — mode='start'(/r_ 명령) | 'date'(날짜 안내 메시지에 단 답장).
    메시지 발송/수정은 여기서 직접(버튼 서명에 chat_id가 필요해서)."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    if not check_internal_auth(request):
        return JsonResponse({'error': 'unauthorized'}, status=401)
    body = _json_body(request)
    short = str(body.get('shortCode') or '').strip().upper()
    chat_id = body.get('chatId')
    telegram_id = str(body.get('fromId') or '').strip() or None
    client = DataRouterClient()
    name = str(body.get('name') or '').strip()
    if name and not short and chat_id is not None:  # "/r 섭외자"
        found = find_open_matches(client, name, chat_id)
        if len(found) != 1:
            text = (_pick_message(name, found, 'r') if found
                    else f'⚠️ [{name}] 결과를 넣을 매칭을 이 지역에서 못 찾았어')
            match_result_input._send(chat_id, text, reply_to=body.get('replyTo'))
            return JsonResponse({'ok': True})
        short = found[0]['short']
    if not short or chat_id is None:
        return JsonResponse({'ok': False})
    if body.get('mode') == 'date':
        kind = str(body.get('kind') or '')
        if kind not in match_result_input.POSTPONE:
            return JsonResponse({'ok': False})
        match_result_input.handle_date_reply(
            client, short, kind, body.get('text'), chat_id, body.get('replyTo'), body.get('promptMessageId'),
            lambda c, sid: _resolve_actor(c, telegram_id, sid))
    else:
        match_result_input.start(client, short, chat_id, body.get('replyTo'))
    return JsonResponse({'ok': True})
