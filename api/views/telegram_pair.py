# telegramPair.js 포팅 — 어드민 쪽 /pair 코드 발급/상태조회/취소/연결해제.
# 실제 코드 완성(봇이 코드를 받아 처리)은 telegram_pair_internal.py 몫.
import json
import secrets

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from api.auth.gate import require_jwt
from api.clients.data_router import DataRouterClient
from api.telegram.team_config import patch_team_config

# 혼동되는 문자(0/O, 1/I/L) 제외 — 대문자+숫자 8자.
CODE_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
CODE_LENGTH = 8
TTL_MINUTES = 10

# 채널 타입 → BROADCAST_SETTINGS.CONFIG 키/라벨. services/main routes/teams.js의
# CHANNEL_DEFS 포팅(welcome 메시지/버튼은 tel_router가 pair-complete 응답을 받아
# 직접 발송하므로 telegram_pair_internal.py 쪽에 둠 — 여기선 field/label/lastMsgIdField만).
CHANNEL_DEFS = {
    'dashboard':       {'field': 'chatId', 'label': '대시보드', 'lastMsgIdField': 'lastMessageId'},
    'stats':           {'field': 'statsChatId', 'label': '일일보고', 'lastMsgIdField': 'lastStatsMsgId'},
    'prayer':          {'field': 'prayerChatId', 'label': '기도문'},
    'matching':        {'field': 'matchingChatId', 'label': '매칭현황판', 'lastMsgIdField': 'lastMatchingMsgId'},
    'prospect':        {'field': 'prospectChatId', 'label': '찾기현황판', 'lastMsgIdField': 'lastProspectMsgId'},
    'feedback':        {'field': 'feedbackChatId', 'label': '매칭피드백', 'lastMsgIdField': 'lastFeedbackMsgId'},
    'returnHome':      {'field': 'returnHomeChatId', 'label': '귀소할일'},
    'community':       {'field': 'communityChatId', 'label': '커뮤니티'},
    'schedule':        {'field': 'scheduleChatId', 'label': '일정방'},
    'activityReport':  {'field': 'activityReportChatId', 'label': '일정통계'},
    'currentSchedule': {'field': 'currentScheduleChatId', 'label': '현재일정'},
    'activityCoord':   {'field': 'activityCoordChatId', 'label': '활동소통'},
    'sheetDashboard':  {'field': 'sheetDashboardChatId', 'label': '섭외명단', 'lastMsgIdField': 'lastSheetDashMsgId'},
    'talkDashboard':   {'field': 'talkDashboardChatId', 'label': '말걸기', 'lastMsgIdField': 'lastTalkDashMsgId'},
    # 135/246 연합(사쉐 통합 대시보드) 전용 — team='135 연합'/'246 연합'일 때만 씀.
    'shedUnified':     {'field': 'shedUnifiedChatId', 'label': '통합현황판', 'lastMsgIdField': 'lastShedMsgId'},
    'tmDash':          {'field': 'tmDashChatId', 'label': 'TM현황', 'lastMsgIdField': 'lastTmMsgId'},
    'schedDash':       {'field': 'schedDashChatId', 'label': '예약타임테이블', 'lastMsgIdField': 'lastSchedMsgId'},
}


def _json_body(request):
    try:
        return json.loads(request.body or b'{}')
    except (TypeError, ValueError):
        return {}


def _generate_code():
    return ''.join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def _pair_command(code):
    suffix = f'@{settings.TELEGRAM_BOT_USERNAME}' if settings.TELEGRAM_BOT_USERNAME else ''
    return f'/pair{suffix} {code}'


@csrf_exempt
@require_jwt
def telegram_pair_start(request, *args, **kwargs):
    """코드 발급 — 이미 대기 중인 코드가 있으면 새로 안 만들고 TTL만 10분 연장."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    team_id = str(body.get('team') or '').strip().rstrip('팀')
    channel_type = str(body.get('channelType') or '').strip()
    if not team_id:
        return JsonResponse({'success': False, 'message': 'team 필요'}, status=400)
    if channel_type not in CHANNEL_DEFS:
        return JsonResponse({'success': False, 'message': 'invalid channelType'}, status=400)

    sabun = request.user['sabun']
    client = DataRouterClient()
    existing = client.query_one(
        "SELECT CODE FROM TELEGRAM_PAIRINGS WHERE TEAM_ID = :1 AND CHANNEL_TYPE = :2 AND COMPLETED_AT IS NULL",
        [team_id, channel_type],
    )
    if existing:
        code = existing['code']
        client.exec(
            "UPDATE TELEGRAM_PAIRINGS SET EXPIRES_AT = SYSTIMESTAMP + INTERVAL '10' MINUTE WHERE CODE = :1",
            [code],
        )
        message = f'⚠️ TTL 갱신됐어! ({TTL_MINUTES}분 추가). 한 번 사용되면 만료돼.'
    else:
        code = None
        for _ in range(3):
            candidate = _generate_code()
            try:
                client.exec(
                    """INSERT INTO TELEGRAM_PAIRINGS (CODE, TEAM_ID, CHANNEL_TYPE, ISSUED_BY_SABUN, EXPIRES_AT)
                       VALUES (:1, :2, :3, :4, SYSTIMESTAMP + INTERVAL '10' MINUTE)""",
                    [candidate, team_id, channel_type, sabun],
                )
                code = candidate
                break
            except Exception:
                continue
        if not code:
            return JsonResponse({'success': False, 'message': '코드 발급 실패, 다시 시도해줘'}, status=500)
        message = f'⚠️ 코드 복사됐어! {TTL_MINUTES}분 안에 텔레그램 방에 붙여넣어줘. 한 번 사용되면 만료돼.'

    return JsonResponse({
        'success': True, 'code': code, 'command': _pair_command(code),
        'ttlMinutes': TTL_MINUTES, 'message': message,
    })


@csrf_exempt
@require_jwt
def telegram_pair_status(request, *args, **kwargs):
    """어드민 화면이 3초 간격으로 폴링 — 봇이 코드를 처리하면 완료로 전환됨."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    team_id = str(body.get('team') or '').strip().rstrip('팀')
    channel_type = str(body.get('channelType') or '').strip()
    if not team_id or channel_type not in CHANNEL_DEFS:
        return JsonResponse({'success': False, 'message': 'team, channelType 필요'}, status=400)

    client = DataRouterClient()
    row = client.query_one(
        """SELECT CODE, COMPLETED_AT, CHAT_ID, CHAT_TITLE,
                  CASE WHEN COMPLETED_AT IS NULL AND EXPIRES_AT < SYSTIMESTAMP THEN 1 ELSE 0 END AS IS_EXPIRED
             FROM TELEGRAM_PAIRINGS WHERE TEAM_ID = :1 AND CHANNEL_TYPE = :2
            ORDER BY ISSUED_AT DESC FETCH FIRST 1 ROWS ONLY""",
        [team_id, channel_type],
    )
    if not row:
        return JsonResponse({'success': True, 'state': 'none'})
    if row['completed_at']:
        return JsonResponse({'success': True, 'state': 'completed', 'chatId': row['chat_id'], 'chatTitle': row['chat_title']})
    if row['is_expired'] == '1':
        return JsonResponse({'success': True, 'state': 'expired'})
    return JsonResponse({'success': True, 'state': 'pending', 'code': row['code']})


@csrf_exempt
@require_jwt
def telegram_pair_disconnect(request, *args, **kwargs):
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    team_id = str(body.get('team') or '').strip().rstrip('팀')
    channel_type = str(body.get('channelType') or '').strip()
    if not team_id or channel_type not in CHANNEL_DEFS:
        return JsonResponse({'success': False, 'message': 'team, channelType 필요'}, status=400)

    channel_def = CHANNEL_DEFS[channel_type]
    field = channel_def['field']
    title_key = field[:-2] + 'Title' if field.endswith('Id') else field + 'Title'
    patch = {field: None, title_key: None}
    if channel_def.get('lastMsgIdField'):
        patch[channel_def['lastMsgIdField']] = None

    client = DataRouterClient()
    patch_team_config(client, team_id, patch, request.user['sabun'])
    return JsonResponse({'success': True, 'message': f"{channel_def['label']} 연결 해제 완료"})


@csrf_exempt
@require_jwt
def telegram_pair_cancel(request, *args, **kwargs):
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    team_id = str(body.get('team') or '').strip().rstrip('팀')
    channel_type = str(body.get('channelType') or '').strip()
    if not team_id or channel_type not in CHANNEL_DEFS:
        return JsonResponse({'success': False, 'message': 'team, channelType 필요'}, status=400)

    client = DataRouterClient()
    client.exec(
        "DELETE FROM TELEGRAM_PAIRINGS WHERE TEAM_ID = :1 AND CHANNEL_TYPE = :2 AND COMPLETED_AT IS NULL",
        [team_id, channel_type],
    )
    return JsonResponse({'success': True, 'message': '취소됐어'})


@csrf_exempt
def telegram_link_me(request, *args, **kwargs):
    # TODO: 텔레그램 미니앱 initData HMAC 검증 — 이번 범위 밖(관리자 채널 연결과 무관).
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/telegramPair.js"}, status=501)
