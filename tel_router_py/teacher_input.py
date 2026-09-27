# 매칭현황판의 "/t_<sarang_id 뒤 8자리> 이름" 탭형 명령 처리 — pairing.py와 동일한 구조.
import logging
import re

import config
import telegram_client

logger = logging.getLogger('tel_router.teacher_input')

TEACHER_CMD_RE = re.compile(r'^/t_([0-9a-fA-F]{8})(?:@\S+)?(?:\s+(.+))?$', re.DOTALL)


def is_teacher_command(text):
    return bool(TEACHER_CMD_RE.match(text.strip()))


def parse_teacher_command(text):
    m = TEACHER_CMD_RE.match(text.strip())
    if not m:
        return None, None
    return m.group(1).upper(), (m.group(2) or '').strip()


def _reply(chat_id, text, reply_to=None):
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
    if reply_to is not None:
        payload['reply_to_message_id'] = reply_to
    telegram_client.enqueue('sendMessage', payload)


async def handle_teacher_message(http_client, message):
    text = (message.get('text') or '').strip()
    chat_id = (message.get('chat') or {}).get('id')
    reply_to = message.get('message_id')
    if chat_id is None:
        return

    short_code, teacher_name = parse_teacher_command(text)
    if not short_code:
        return
    if not teacher_name:
        _reply(chat_id, f'🎓 교사 이름도 같이 적어줘. 예) <code>/t_{short_code.lower()} 홍길동</code>', reply_to)
        return

    try:
        resp = await http_client.post(
            f'{config.MAIN_SERVER_URL}/internal/telegram/teacher-assign',
            json={'shortCode': short_code, 'teacherName': teacher_name},
            headers={'Authorization': f'Bearer {config.MAIN_INTERNAL_TELEGRAM_TOKEN}'},
            timeout=10.0,
        )
        result = resp.json()
    except Exception:
        logger.exception('teacher-assign call failed')
        _reply(chat_id, '🚫 잠시 후 다시 시도해줘. (서버 연결 실패)', reply_to)
        return

    _reply(chat_id, result.get('message') or '⚠️ 처리 실패', reply_to)
