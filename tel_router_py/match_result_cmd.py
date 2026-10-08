# 매칭현황판 "/r_<사랑이 뒤 8자리>" 명령과 날짜 안내 메시지 답장을 main(Django)으로 넘김 — 버튼/저장/메시지는 main이 처리
import logging
import re

import config
import telegram_client

logger = logging.getLogger('tel_router.match_result_cmd')

CMD_RE = re.compile(r'^/r_([0-9a-fA-F]{8})(?:@\S+)?\s*$')
NAME_RE = re.compile(r'^/r(?:@\S+)?(?:\s+(\S+))?\s*$')  # "/r 섭외자" — 이름으로(그 방 지역에서 main이 찾음)
# main이 날짜 안내 메시지 끝에 붙이는 꼬리표(#r_<8자리><D|S>) — 답장이 어느 건/어느 결과인지 상태 없이 알아냄
DATE_TAG_RE = re.compile(r'#r_([0-9A-Fa-f]{8})([DS])')


def is_command(text):
    t = text.strip()
    return bool(CMD_RE.match(t) or NAME_RE.match(t))


def date_reply_target(message):
    """봇의 날짜 안내 메시지에 단 답장이면 (short, kind, 안내 메시지 id), 아니면 None."""
    target = message.get('reply_to_message') or {}
    if not (target.get('from') or {}).get('is_bot'):
        return None
    m = DATE_TAG_RE.search(target.get('text') or '')
    return (m.group(1).upper(), m.group(2), target.get('message_id')) if m else None


async def _forward(http_client, body):
    try:
        await http_client.post(
            f'{config.MAIN_SERVER_URL}/internal/telegram/match-result',
            json=body,
            headers={'Authorization': f'Bearer {config.MAIN_INTERNAL_TELEGRAM_TOKEN}'},
            timeout=10.0,
        )
    except Exception:
        logger.exception('match-result forward failed')


async def handle_command(http_client, message):
    text = (message.get('text') or '').strip()
    chat_id = (message.get('chat') or {}).get('id')
    if chat_id is None:
        return
    body = {'mode': 'start', 'chatId': chat_id, 'replyTo': message.get('message_id'),
            'fromId': str((message.get('from') or {}).get('id') or '')}
    m = CMD_RE.match(text)
    if m:
        body['shortCode'] = m.group(1).upper()
    else:
        m = NAME_RE.match(text)
        if not m or not m.group(1):
            telegram_client.enqueue('sendMessage', {
                'chat_id': chat_id, 'parse_mode': 'HTML', 'reply_to_message_id': message.get('message_id'),
                'text': '🛡️ <code>/r 섭외자</code> 처럼 보내줘. 예) <code>/r 홍길동</code>'})
            return
        body['name'] = m.group(1)
    await _forward(http_client, body)


async def handle_date_reply(http_client, message, target):
    short, kind, prompt_id = target
    await _forward(http_client, {
        'mode': 'date', 'shortCode': short, 'kind': kind, 'text': message.get('text') or '',
        'chatId': (message.get('chat') or {}).get('id'), 'replyTo': message.get('message_id'),
        'promptMessageId': prompt_id, 'fromId': str((message.get('from') or {}).get('id') or ''),
    })
