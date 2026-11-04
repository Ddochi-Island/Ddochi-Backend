# 합당한 자 데이터를 바꾸는 API가 성공하면 tel_router(/notify)에 "바뀜" 신호 — 보고 있는 다른 사람 화면이 바로 새로고침.
# 신호는 백그라운드 스레드로 보내고 실패해도 무시(응답을 늦추거나 깨지 않게).
import logging
import threading

import requests
from django.conf import settings

logger = logging.getLogger('api.realtime')

# 경로 끝부분 → 토픽. hapdang = 목록 다시 불러오기, calls = 통화 중 표시만
_TOPICS = {
    # 합당한 자 화면·합재양·매칭
    'submit-result': 'hapdang', 'delete-log': 'hapdang', 'run-shed-gacha': 'hapdang', 'cancel-shed-habjaeyang': 'hapdang',
    'shed-register': 'hapdang', 'shed-reject-duplicate': 'hapdang', 'shed-reject': 'hapdang', 'shed-revive': 'hapdang',
    'shed-pending-reject': 'hapdang', 'shed-pending-revive': 'hapdang', 'shed-webhook': 'hapdang', 'shed/memo': 'hapdang',
    'submit-habjaeyang-new': 'hapdang', 'habjaeyang-dup-resolve': 'hapdang', 'update-approval': 'hapdang',
    'toggle-hj-status': 'hapdang', 'edit-match': 'hapdang', 'update-match': 'hapdang', 'postpone-meeting': 'hapdang',
    # 텔레그램 버튼·명령, shed 신청 동기화(내부 경로)
    'telegram/callback': 'hapdang', 'telegram/match-result': 'hapdang', 'telegram/teacher-assign': 'hapdang',
    'sync-intake': 'hapdang',
    # 통화 시작/끝
    'shed-call-start': 'calls', 'shed-call-end': 'calls',
}


def topic_for(method, path, status):
    if method != 'POST' or not (200 <= status < 300):
        return None
    for prefix in ('/api/', '/internal/'):
        if path.startswith(prefix):
            return _TOPICS.get(path[len(prefix):].strip('/'))
    return None


def _send(topic, by):
    try:
        requests.post(f"{settings.TEL_ROUTER_URL.rstrip('/')}/notify", json={'topic': topic, 'by': by},
                      headers={'X-Enqueue-Secret': settings.TEL_ROUTER_ENQUEUE_SECRET}, timeout=3)
    except Exception:
        logger.warning('[realtime] notify failed', exc_info=True)


class RealtimeNotifyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        topic = topic_for(request.method, request.path, response.status_code)
        if topic:
            user = getattr(request, 'user', None)
            by = user.get('sabun') if isinstance(user, dict) else None  # require_jwt가 넣는 dict
            threading.Thread(target=_send, args=(topic, by), daemon=True).start()
        return response


if __name__ == '__main__':  # python -m api.realtime_middleware — 경로 분류 자체 점검
    assert topic_for('POST', '/api/submit-result', 200) == 'hapdang'
    assert topic_for('POST', '/api/shed/memo', 200) == 'hapdang'
    assert topic_for('POST', '/api/shed-call-start', 200) == 'calls'
    assert topic_for('POST', '/internal/telegram/callback', 200) == 'hapdang'
    assert topic_for('POST', '/api/get-shed-prospects', 200) is None
    assert topic_for('POST', '/api/shed-call-status', 200) is None
    assert topic_for('POST', '/api/submit-result', 400) is None
    assert topic_for('GET', '/api/submit-result', 200) is None
    print('ok')
