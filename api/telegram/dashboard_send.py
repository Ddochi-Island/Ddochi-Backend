# 찾기현황판/매칭현황판/일일보고 공용 — 정각 크론의 "새 메시지 발송 + 이전 삭제"
# 로직. 단, 날짜가 바뀐 뒤 첫 발송이면 전날 마지막 메시지는 지우지 않고 그대로
# 남겨서 하루치 마지막 기록을 보존한다(레거시의 22시 업무일 마감 스냅샷 보존과
# 같은 취지 — 이 프로젝트엔 업무일 개념이 없어 캘린더 날짜(자정, KST) 기준으로
# 단순화). 같은 날 안에서는 지금까지처럼 매시 삭제+재발송.
import datetime
import logging

from api.telegram import tel_router_client
from api.telegram.team_config import patch_team_config

logger = logging.getLogger('api.telegram.dashboard_send')


def in_broadcast_window(start_hour=6, end_hour=23):
    """정각 발송 시간대(06~23시) 밖이면 웹 이벤트로 인한 edit도 건너뜀 — 그 시간대
    바깥에 떠 있는 메시지는 전날의 마감 기록이라 더 이상 손대지 않기 위함."""
    return start_hour <= datetime.datetime.now().hour <= end_hour


def send_fresh_dashboard(client, region_code, chat_id, text, reply_markup, cfg, msg_id_field, msg_date_field, log_tag):
    """cfg는 호출부가 이미 조회해둔 team config — chat_id/이전 메시지 정보 재사용."""
    today = datetime.date.today().isoformat()
    try:
        result = tel_router_client.enqueue(
            'sendMessage', {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': reply_markup}, await_result=True,
        )
    except Exception:
        logger.warning('[%s] send_fresh sendMessage failed', log_tag, exc_info=True)
        return {'sent': False}

    if not result.get('ok'):
        logger.warning('[%s] send_fresh sendMessage rejected: %s', log_tag, result.get('description'))
        return {'sent': False}

    new_msg_id = result.get('result', {}).get('message_id')
    if not new_msg_id:
        return {'sent': True, 'deletedPrevious': False}

    previous_msg_id = cfg.get(msg_id_field)
    previous_msg_date = cfg.get(msg_date_field)
    patch_team_config(client, region_code, {msg_id_field: new_msg_id, msg_date_field: today}, 'system')

    if not previous_msg_id or str(previous_msg_id) == str(new_msg_id):
        return {'sent': True, 'newMessageId': new_msg_id, 'deletedPrevious': False}

    if previous_msg_date != today:
        # 전날 마지막 메시지 — 삭제하지 않고 하루치 기록으로 남겨둠.
        return {'sent': True, 'newMessageId': new_msg_id, 'deletedPrevious': False, 'keptPreviousDayRecord': True}

    try:
        tel_router_client.enqueue('deleteMessage', {'chat_id': chat_id, 'message_id': previous_msg_id})
    except Exception:
        logger.warning('[%s] delete previous message failed', log_tag, exc_info=True)
    return {'sent': True, 'newMessageId': new_msg_id, 'deletedPrevious': True}
