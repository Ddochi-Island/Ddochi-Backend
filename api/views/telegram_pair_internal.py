# telegramPair.js의 /internal 라우터 포팅 — tel_router(텔레그램 봇 웹훅을 처리하는
# 별도 서비스)가 그룹챗에서 "/pair CODE"를 감지하면 이 엔드포인트를 호출해서
# 페어링을 완성함(main은 텔레그램 API를 직접 안 부름 — 봇 세션은 tel_router 쪽에만 있어서
# 환영 메시지 발송도 tel_router가 이 응답의 welcomeText/welcomeButton을 보고 직접 함).
import json
import logging
import time

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from api.clients.data_router import DataRouterClient
from api.telegram.internal_auth import check_internal_auth
from api.telegram.matching_dashboard import refresh_matching_dashboard
from api.telegram.prospect_dashboard import refresh_prospect_dashboard
from api.telegram.team_config import patch_team_config
from api.views.telegram_pair import CHANNEL_DEFS


def _json_body(request):
    try:
        return json.loads(request.body or b'{}')
    except (TypeError, ValueError):
        return {}


# 채널별 환영 메시지 텍스트/버튼 — services/main routes/teams.js CHANNEL_DEFS의
# welcome/button 그대로. 이 프로젝트엔 TEAMS.DISPLAY_NAME이 없어서 팀 이름 자리엔
# TEAM_ID(REGION_CODE) 코드값을 그대로 씀.
_WELCOME = {
    'dashboard':       {'text': lambda t: f'👋 [{t}] 또치섬 대시보드가 연결되었어!', 'button': ('입국하기 🛫', '?startapp=dailyReport')},
    'prayer':          {'text': lambda t: f'🙏 [{t}] 향연(기도문) 방이 연결되었어! 이제 이곳에 향연이 피어오를거야.', 'button': ('🙏 향 붙이러 가기', '?startapp=prayer')},
    'feedback':        {'text': lambda t: f'📋 [{t}] 매칭피드백 방이 연결되었어!', 'button': ('센터 가보자! 🏃', '?startapp=center')},
    'returnHome':      {'text': lambda t: f'🏠 [{t}] 귀소할일 알림방이 연결되었어!'},
    'community':       {'text': lambda t: f'📖 [{t}] 전도 노트(커뮤니티) 알림방이 연결되었어!'},
    'schedule':        {'text': lambda t: f'🌅 [{t}] 아침 일정 브리핑 방이 연결되었어!'},
    'activityReport':  {'text': lambda t: f'📊 [{t}] 일정통계 전송방이 연결되었어! 설정한 시간에 자동으로 활동 현황이 전송될거야.'},
    'currentSchedule': {'text': lambda t: f'🏔 [{t}] 현재일정 전송방이 연결되었어! "지금 우리 시온산은" 메시지가 설정한 시간에 발송돼.'},
    'activityCoord':   {'text': lambda t: f"🫵 [{t}] 활동소통 방이 연결되었어! '대학 너 나와' 메시지가 이곳에 발송돼."},
    'sheetDashboard':  {'text': lambda t: f'📋 [{t}] 섭외 명단 대시보드 방이 연결되었어! 매일 09:00에 새로운 유입 + 부재중 현황이 발송돼.'},
    'talkDashboard':   {'text': lambda t: f'🗣️ [{t}] 말걸기 대시보드 방이 연결되었어! 일일보고 제출 시 자동으로 갱신돼.'},
}


@csrf_exempt
def telegram_pair_complete(request, *args, **kwargs):
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    if not check_internal_auth(request):
        return JsonResponse({'error': 'unauthorized'}, status=401)

    body = _json_body(request)
    code = str(body.get('code') or '').strip().upper()
    chat_id = str(body.get('chatId') or '').strip()
    chat_title = str(body.get('chatTitle') or '')[:200]
    if not code or not chat_id:
        return JsonResponse({'error': 'code, chatId required'}, status=400)

    client = DataRouterClient()
    # race condition 안전망 — 어드민이 "복사" 직후 바로 붙여넣으면 INSERT commit
    # 가시성 timing 차이로 not_found 뜰 수 있어서 300ms 대기 후 1회 재조회.
    row = client.query_one(
        """SELECT TEAM_ID, CHANNEL_TYPE, ISSUED_BY_SABUN, COMPLETED_AT,
                  CASE WHEN EXPIRES_AT < SYSTIMESTAMP THEN 1 ELSE 0 END AS IS_EXPIRED
             FROM TELEGRAM_PAIRINGS WHERE CODE = :1""",
        [code],
    )
    if not row:
        time.sleep(0.3)
        row = client.query_one(
            """SELECT TEAM_ID, CHANNEL_TYPE, ISSUED_BY_SABUN, COMPLETED_AT,
                      CASE WHEN EXPIRES_AT < SYSTIMESTAMP THEN 1 ELSE 0 END AS IS_EXPIRED
                 FROM TELEGRAM_PAIRINGS WHERE CODE = :1""",
            [code],
        )
    if not row:
        return JsonResponse({'state': 'not_found'})
    if row['completed_at']:
        return JsonResponse({'state': 'already_used'})
    if row['is_expired'] == '1':
        return JsonResponse({'state': 'expired'})

    client.exec(
        "UPDATE TELEGRAM_PAIRINGS SET COMPLETED_AT = SYSTIMESTAMP, CHAT_ID = :1, CHAT_TITLE = :2 WHERE CODE = :3",
        [chat_id, chat_title or None, code],
    )

    team_id = row['team_id']
    channel_type = row['channel_type']
    channel_def = CHANNEL_DEFS.get(channel_type)
    if not channel_def:
        return JsonResponse({
            'state': 'completed', 'warning': 'channel_def_not_found',
            'team': team_id, 'channelType': channel_type, 'chatTitle': chat_title,
        })

    field = channel_def['field']
    title_key = field[:-2] + 'Title' if field.endswith('Id') else field + 'Title'
    patch = {field: chat_id, title_key: chat_title or None}
    if channel_def.get('lastMsgIdField'):
        # 재연동 시 이전 채널의 메시지 ID로 edit 시도하지 않도록 초기화.
        patch[channel_def['lastMsgIdField']] = None

    author = row['issued_by_sabun'] or 'tel_router-pair'
    patch_team_config(client, team_id, patch, author)

    if channel_type == 'prospect':
        try:
            refresh_prospect_dashboard(client, team_id, allow_create=True)
        except Exception:
            logging.getLogger('api.views.telegram_pair_internal').warning(
                '[telegram_pair_complete] prospect dashboard initial send failed', exc_info=True,
            )
    elif channel_type == 'matching':
        try:
            refresh_matching_dashboard(client, team_id, allow_create=True)
        except Exception:
            logging.getLogger('api.views.telegram_pair_internal').warning(
                '[telegram_pair_complete] matching dashboard initial send failed', exc_info=True,
            )

    # TEAMS.DISPLAY_NAME이 없는 프로젝트라 팀 이름 자리엔 TEAM_ID(REGION_CODE) 그대로.
    team_name = team_id
    welcome = _WELCOME.get(channel_type)
    welcome_text = welcome['text'](team_name) if welcome else None
    welcome_button = None
    link_base = settings.MY_TELEGRAM_LINK
    if welcome and welcome.get('button') and link_base:
        btn_text, btn_path = welcome['button']
        welcome_button = {'text': btn_text, 'url': f'{link_base}{btn_path}'}

    return JsonResponse({
        'state': 'completed', 'team': team_id, 'teamName': team_name,
        'channelType': channel_type, 'label': channel_def['label'], 'chatTitle': chat_title or None,
        'welcomeText': welcome_text, 'welcomeButton': welcome_button,
    })
