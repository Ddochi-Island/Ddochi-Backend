# 인라인 버튼 callback_query 처리 — HMAC 검증 후 main(Django)에 위임, 결과 toast로 응답
import logging

import config
import telegram_client
from hmac_verify import verify_callback_data

logger = logging.getLogger('tel_router.callback')


async def handle_callback_query(http_client, cq):
    callback_query_id = cq.get('id')
    data = cq.get('data')
    message = cq.get('message') or {}
    chat_id = (message.get('chat') or {}).get('id')
    message_id = message.get('message_id')
    from_id = (cq.get('from') or {}).get('id')

    verdict = verify_callback_data(config.CALLBACK_HMAC_SECRET, data, chat_id, config.CALLBACK_TS_WINDOW_MS)
    if not verdict['ok']:
        logger.warning('callback rejected: %s', verdict['reason'])
        if callback_query_id:
            telegram_client.enqueue('answerCallbackQuery', {
                'callback_query_id': callback_query_id, 'text': '⚠️ 만료되었거나 잘못된 버튼이야',
            })
        return

    toast = '⚠️ 처리 실패'
    try:
        resp = await http_client.post(
            f'{config.MAIN_SERVER_URL}/internal/telegram/callback',
            json={
                'action': verdict['action'], 'args': verdict['args'],
                'chatId': chat_id, 'messageId': message_id, 'fromId': str(from_id or ''),
            },
            headers={'Authorization': f'Bearer {config.MAIN_INTERNAL_TELEGRAM_TOKEN}'},
            timeout=10.0,
        )
        result = resp.json()
        toast = result.get('toast') or '✅'
    except Exception:
        logger.exception('callback dispatch to main failed')

    if callback_query_id:
        telegram_client.enqueue('answerCallbackQuery', {'callback_query_id': callback_query_id, 'text': toast})
