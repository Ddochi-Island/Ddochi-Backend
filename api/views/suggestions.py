# 개발자에게 건의하기 — 제출(홈 화면) + 건의함 목록(관리자 화면). services/main/src/routes/suggestions.js 포팅
import logging
import uuid

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from api.auth.gate import require_jwt
from api.clients.data_router import DataRouterClient
from api.telegram import tel_router_client
from api.views.daily_report import _json_body

logger = logging.getLogger('api.views.suggestions')

# 개발자 알림 방 — 레거시 SUGGESTION_CHAT_ID(-5495814189)가 슈퍼그룹으로 전환되면서 번호가 바뀜
# (텔레그램 migrate_to_chat_id, 2026-09-29 확인). 봇이 그 방 멤버여야 알림이 감.
SUGGESTION_CHAT_ID = -1004435642724


@csrf_exempt
@require_jwt
def suggestions_submit(request, *args, **kwargs):
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    subject = str(body.get('subject') or '').strip()
    content = str(body.get('content') or '').strip()
    if not subject:
        return JsonResponse({'success': False, 'message': '주제를 입력해주세요.'}, status=400)
    if not content:
        return JsonResponse({'success': False, 'message': '내용을 입력해주세요.'}, status=400)

    sabun = request.user['sabun']
    name = request.user.get('name') or ''
    client = DataRouterClient()
    num = client.query_one('SELECT SUGGESTIONS_SEQ.NEXTVAL AS NUM FROM DUAL')['num']
    client.exec(
        """INSERT INTO SUGGESTIONS (SUGGESTION_ID, SUGGESTION_NUM, AUTHOR_MEMBER_ID, AUTHOR_NAME, SUBJECT, CONTENT)
           VALUES (:1, :2, :3, :4, :5, :6)""",
        [uuid.uuid4().hex.upper(), num, sabun, name[:50], subject[:200], content],
    )

    try:
        tel_router_client.enqueue('sendMessage', {
            'chat_id': SUGGESTION_CHAT_ID,
            'text': f'📬 건의가 도착했어요 #{num}\n\n이름: {name}\n주제: {subject}\n내용:\n{content}'[:4000],
        })
    except Exception:
        logger.warning('[suggestions] telegram send failed', exc_info=True)

    return JsonResponse({'success': True})


@csrf_exempt
@require_jwt
def suggestions_list(request, *args, **kwargs):
    # 레거시는 로그인만 하면 누구나 조회 가능했지만, 건의 내용이 전원에게 노출될 이유가 없어서 관리자로 제한.
    # 관리자 화면은 직책이 아니라 비밀번호(admin-unlock → adminUnlocked 클레임)로 들어가므로 그걸 우선 인정하고,
    # 직책상 관리자(SCOPE='global' — 관리자/수지역장)도 허용.
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    client = DataRouterClient()
    is_admin = request.user.get('adminUnlocked') or client.query_one(
        """SELECT 1 AS OK FROM MEMBER_POSITION_MAPPINGS mpm
             JOIN POSITION_CODES pc ON pc.POSITION_CODE = mpm.POSITION_CODE
            WHERE mpm.MEMBER_ID = :1 AND pc.SCOPE = 'global'""",
        [request.user['sabun']],
    )
    if not is_admin:
        return JsonResponse({'success': False, 'message': '관리자만 볼 수 있어'}, status=403)

    rows = client.query(
        """SELECT SUGGESTION_NUM AS NUM, AUTHOR_NAME, SUBJECT, CONTENT,
                  TO_CHAR(CREATED_AT AT TIME ZONE 'Asia/Seoul', 'YYYY-MM-DD HH24:MI') AS CREATED_AT
             FROM SUGGESTIONS ORDER BY CREATED_AT DESC""",
        fetch_limit=200,
    )
    return JsonResponse({'success': True, 'list': rows})
