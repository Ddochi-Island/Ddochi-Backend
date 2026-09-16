# "/pair CODE" 명령 파싱 + main(Django) 페어링 완료 요청 — services/tel_router/src/webhook/handler.js 포팅
import html
import logging
import re

import config
import telegram_client

logger = logging.getLogger('tel_router.pairing')

PAIR_TRIGGER_RE = re.compile(r'^/pair\b', re.IGNORECASE)
PAIR_CODE_RE = re.compile(r'^/pair(?:@\S+)?\s+([A-Za-z0-9]+)$', re.IGNORECASE)


def is_pair_command(text):
    return bool(PAIR_TRIGGER_RE.match(text.strip()))


def parse_pair_code(text):
    m = PAIR_CODE_RE.match(text.strip())
    return m.group(1).upper() if m else None


def _reply(chat_id, text, reply_to=None, reply_markup=None):
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
    if reply_to is not None:
        payload['reply_to_message_id'] = reply_to
    if reply_markup is not None:
        payload['reply_markup'] = reply_markup
    telegram_client.enqueue('sendMessage', payload)


async def handle_pair_message(http_client, message):
    text = (message.get('text') or '').strip()
    chat = message.get('chat') or {}
    chat_id = chat.get('id')
    chat_title = chat.get('title') or chat.get('first_name') or ''
    from_id = (message.get('from') or {}).get('id')
    reply_to = message.get('message_id')
    if chat_id is None:
        return

    code = parse_pair_code(text)
    if code is None:
        _reply(chat_id, '🚫 형식이 안 맞아. <code>/pair A1B2C3D4</code> 처럼 입력해줘.', reply_to)
        return

    try:
        resp = await http_client.post(
            f'{config.MAIN_SERVER_URL}/internal/telegram/pair-complete',
            json={'code': code, 'chatId': str(chat_id), 'chatTitle': chat_title, 'fromUser': str(from_id or '')},
            headers={'Authorization': f'Bearer {config.MAIN_INTERNAL_TELEGRAM_TOKEN}'},
            timeout=10.0,
        )
        result = resp.json()
    except Exception:
        logger.exception('pair-complete call failed')
        _reply(chat_id, '🚫 잠시 후 다시 시도해줘. (서버 연결 실패)', reply_to)
        return

    state = result.get('state')
    if state == 'completed':
        team_name = result.get('teamName') or result.get('team') or '팀'
        label = result.get('label') or result.get('channelType') or '채널'
        title = result.get('chatTitle') or chat_title or '(이름 없음)'
        _reply(chat_id, f'✅ <b>{team_name}</b> [{label}] 채널로 등록됐어!\n방 이름: <b>{html.escape(title)}</b>', reply_to)
        welcome_text = result.get('welcomeText')
        if welcome_text:
            reply_markup = None
            welcome_button = result.get('welcomeButton')
            if welcome_button:
                reply_markup = {'inline_keyboard': [[welcome_button]]}
            _reply(chat_id, welcome_text, reply_markup=reply_markup)
    elif state == 'already_used':
        _reply(chat_id, '🚫 이미 사용된 코드야. 설정에서 새로 발급해줘.', reply_to)
    elif state == 'expired':
        _reply(chat_id, '🚫 만료된 코드야. 설정에서 새로 발급해줘.', reply_to)
    elif state == 'not_found':
        _reply(chat_id, '🚫 코드를 확인할 수 없어. 설정에서 새로 발급해줘.', reply_to)
    else:
        logger.warning('unknown pair state: %s', state)
