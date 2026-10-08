# 매칭현황판 교사 입력 — "/t 섭외자 교사"(이름) 또는 "/t_<sarang_id 뒤 8자리> 교사"(같은 이름이 여럿일 때). pairing.py와 동일한 구조.
import logging
import re

import config
import telegram_client

logger = logging.getLogger('tel_router.teacher_input')

TEACHER_CMD_RE = re.compile(r'^/t_([0-9a-fA-F]{8})(?:@\S+)?(?:\s+(.+))?$', re.DOTALL)
# "/t 섭외자 교사" — 이름으로(2026-10-08, 현황판 행마다 코드 명령을 다는 대신). 섭외자 찾기는 main이 그 방 지역에서.
TEACHER_NAME_RE = re.compile(r'^/t(?:@\S+)?(?:\s+(\S+)(?:\s+(.+))?)?$', re.DOTALL)
USAGE = '🎓 <code>/t 섭외자 교사</code> 처럼 보내줘. 예) <code>/t 홍길동 김철수</code> (타지역 교사는 <code>김철수(타지역)</code>, 해제는 <code>-</code>)'


def is_teacher_command(text):
    t = text.strip()
    return bool(TEACHER_CMD_RE.match(t) or TEACHER_NAME_RE.match(t))


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
    body = {'chatId': chat_id}
    if short_code:
        if not teacher_name:
            _reply(chat_id, f'🎓 교사 이름도 같이 적어줘. 예) <code>/t_{short_code.lower()} 홍길동</code>', reply_to)
            return
        body.update(shortCode=short_code, teacherName=teacher_name)
    else:
        m = TEACHER_NAME_RE.match(text)
        if not m or not m.group(1) or not (m.group(2) or '').strip():
            _reply(chat_id, USAGE, reply_to)
            return
        body.update(name=m.group(1), teacherName=m.group(2).strip())

    try:
        resp = await http_client.post(
            f'{config.MAIN_SERVER_URL}/internal/telegram/teacher-assign',
            json=body,
            headers={'Authorization': f'Bearer {config.MAIN_INTERNAL_TELEGRAM_TOKEN}'},
            timeout=10.0,
        )
        result = resp.json()
    except Exception:
        logger.exception('teacher-assign call failed')
        _reply(chat_id, '🚫 잠시 후 다시 시도해줘. (서버 연결 실패)', reply_to)
        return

    _reply(chat_id, result.get('message') or '⚠️ 처리 실패', reply_to)
