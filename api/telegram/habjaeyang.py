# 합재양 카드 텔레그램 발송/갱신 — services/main/src/telegram/habjaeyang.js 포팅.
# 데이터 출처가 SARANG_* 스키마로 바뀌어서 쿼리/필드는 새로 짰지만, 메시지 포맷(v2)과
# 인라인 버튼(답장/창개설/재가) 구조는 원본 그대로 따라감.
import datetime
import logging

from django.conf import settings

from api.telegram import tel_router_client
from api.telegram.callback_hmac import sign_callback_data
from api.telegram.prospect_dashboard import refresh_prospect_dashboard
from api.telegram.team_config import load_team_config

logger = logging.getLogger('api.telegram.habjaeyang')

HJ_SHORT = {'reply': 'r', 'window': 'w', 'approve': 'a', 'noop': 'n'}


def build_hj_keyboard(sarang_id, secret, chat_id, replied, window_opened, approval_status):
    def cb(code):
        if secret and chat_id is not None:
            return sign_callback_data(secret, 'hj', f'{sarang_id}.{code}', chat_id)
        return f'hj|{sarang_id}|{code}'

    rows = [[
        {'text': '✅ 답장 💬' if replied else '💬 답장', 'callback_data': cb(HJ_SHORT['reply'])},
        {'text': '✅ 창개설 🚪' if window_opened else '🚪 창개설', 'callback_data': cb(HJ_SHORT['window'])},
    ]]

    if approval_status == 'approved':
        rows.append([{'text': '🎉 재가 완료', 'callback_data': cb(HJ_SHORT['noop'])}])
    elif approval_status == 'rejected':
        rows.append([{'text': '🚫 반려됨', 'callback_data': cb(HJ_SHORT['noop'])}])
    elif replied and window_opened:
        rows.append([{'text': '🛡️ 재가', 'callback_data': cb(HJ_SHORT['approve'])}])

    rows.append([{'text': '❌ 반려하기 (웹앱)', 'url': 'https://page.ddochi.cloud/#/matching'}])
    return {'inline_keyboard': rows}


def _fetch(client, sarang_id):
    return client.query_one(
        """SELECT s.SARANG_ID, s.AGE, s.GENDER, s.MBTI, s.INFLOW_MEMBER_ID,
                  spi.NAME AS PI_NAME, spi.PHONE AS PI_PHONE, spi.RESIDENCE_STATION,
                  hj.HAB_JAE_YANG_ID, hj.ROUTE, hj.TOOL,
                  hj.MATCH_SCHEDULED_AT, hj.MATCH_LOCATION,
                  hj.GWACHEON_TRAVEL_TIME, hj.GWACHEON_TRANSFER_COUNT,
                  hj.CENTER_TRAVEL_TIME, hj.CENTER_TRANSFER_COUNT,
                  hj.SCHOOL_MAJOR_JOB, hj.SCHEDULE, hj.ENVIRONMENT_1Y, hj.APPLICATION_PURPOSE,
                  hj.SELF_IMAGE, hj.DESIRED_IMAGE, hj.CHARACTER_NOTE, hj.ALERT_NOTE, hj.DISTANCE_BURDEN, hj.ETC,
                  hj.HAS_CENTER_ENV, hj.IS_TAKING_MEDS, hj.HAS_MENTAL_ILLNESS,
                  hj.HAS_REPLIED, hj.IS_WINDOW_OPENED, hj.APPROVAL_STATUS, hj.TELEGRAM_MSG_ID,
                  gm.NAME AS GUIDE_NAME, cm.NAME AS CALLER_NAME,
                  mah.REGION_CODE AS TEAM_ID
             FROM SARANG s
             JOIN SARANG_PERSONAL_INFO spi ON spi.PERSONAL_INFO_ID = s.PERSONAL_INFO_ID
             LEFT JOIN SARANG_HAB_JAE_YANG hj ON hj.SARANG_ID = s.SARANG_ID AND hj.IS_ACTIVE = 1
             LEFT JOIN MEMBERS gm ON gm.MEMBER_ID = hj.GUIDE_MEMBER_ID
             LEFT JOIN MEMBERS cm ON cm.MEMBER_ID = hj.CALLER_MEMBER_ID
             LEFT JOIN MEMBER_AFFILIATION_HISTORIES mah
               ON mah.MEMBER_ID = s.INFLOW_MEMBER_ID AND mah.IS_CURRENT = 1
            WHERE s.SARANG_ID = :1""",
        [sarang_id],
    )


def _ox_label(v):
    return 'O' if str(v) == '1' else ('X' if str(v) == '0' else '-')


def _travel_label(minutes, transfers):
    if minutes is None:
        return '미정'
    transfer_label = f'{transfers}회' if transfers is not None else '미정'
    return f'{minutes}분, 환승 {transfer_label}'


def _build_text(row):
    week = ['일', '월', '화', '수', '목', '금', '토']
    mt_date = (row['match_scheduled_at'] or '')[:10] if row['match_scheduled_at'] else ''
    mt_time = (row['match_scheduled_at'] or '')[11:16] if row['match_scheduled_at'] else ''
    day_str = ''
    if mt_date:
        try:
            day_str = week[(datetime.date.fromisoformat(mt_date).weekday() + 1) % 7]
        except ValueError:
            day_str = ''

    path = row['route'] or ''
    tool = row['tool'] or ''
    path_info = path + (f'({tool})' if tool and tool not in path else '')

    gwacheon = _travel_label(row['gwacheon_travel_time'], row['gwacheon_transfer_count'])
    center = _travel_label(row['center_travel_time'], row['center_transfer_count'])

    return (
        f"🐑 대학 {row['team_id'] or '-'}지역의 합재양 🐑\n"
        f"[청년회 통합 Ver.]\n"
        f"- 인도자/티엠자 : {row['guide_name'] or '-'} / {row['caller_name'] or '-'}\n"
        f"- 섭외유형(도구) : {path_info or '-'}\n"
        f"- 매칭 일시/장소 : {mt_date or '-'}({day_str}) {mt_time or ''} {row['match_location'] or ''}\n\n"
        f"▪️ 인적사항\n"
        f"• 이름(성별/나이) : {row['pi_name'] or '-'}({row['gender'] or '-'}/{row['age'] or '-'})\n"
        f"• 연락처 : {row['pi_phone'] or '-'}\n"
        f"• 거주지 : {row['residence_station'] or '-'}\n"
        f"(과천까지 {gwacheon})\n"
        f"(센터까지 {center})\n"
        f"• MBTI : {row['mbti'] or '-'}\n\n"
        f"▪️ 환경\n"
        f"• 학교(전공)/직장 : {row['school_major_job'] or '-'}\n"
        f"• 일정(학원, 동아리, 학생회, 알바 등) : {row['schedule'] or '-'}\n"
        f"• 1년 환경 구체적으로(군입대, 여행, 수술, 본가이동 등) : {row['environment_1y'] or '-'}\n\n"
        f"▪️ 내면\n"
        f"• 신청 목적(메리트) : {row['application_purpose'] or '-'}\n"
        f"• 내가 생각하는 나의 이미지(성격) : {row['self_image'] or '-'}\n"
        f"• 되고 싶은 내적 이미지(or 가장 고민되는 부분) : {row['desired_image'] or '-'}\n\n"
        f"▪️ 기타\n"
        f"• 인성(전화 태도) : {row['character_note'] or '-'}\n"
        f"• 경계 : {row['alert_note'] or '-'}\n"
        f"• 거리부담 : {row['distance_burden'] or '-'}\n"
        f"• 특이사항 : {row['etc'] or '-'}\n\n"
        f"▪️ 합자 체크\n"
        f"• 센터 환경 : {_ox_label(row['has_center_env'])}\n"
        f"• 약물복용 : {_ox_label(row['is_taking_meds'])}\n"
        f"• 정신질환 : {_ox_label(row['has_mental_illness'])}"
    )


def send_habjaeyang_to_telegram(client, sarang_id, refresh_dashboard=True):
    """합재양 저장 직후 호출 — 찾기현황판(없으면 매칭현황판) 채팅방에 카드를 올리거나
    (기존 메시지가 있으면) 수정한다. 실패해도 예외를 던지지 않고 조용히 skip — 저장
    자체를 막을 이유가 없는 부가 기능이라 호출부는 try/except로 감쌀 필요 없음.
    refresh_dashboard=False는 prospect_dashboard.py의 누락 카드 백필에서 씀 — 그쪽이
    이 함수를 호출한 직후 스스로 리스트를 다시 그리므로 여기서 또 갱신하면 중복."""
    row = _fetch(client, sarang_id)
    if not row or not row['hab_jae_yang_id']:
        return {'skipped': True, 'reason': 'no_habjaeyang'}
    if not row['team_id']:
        return {'skipped': True, 'reason': 'team_missing'}

    cfg = load_team_config(client, row['team_id'])
    chat_id = cfg.get('prospectChatId') or cfg.get('matchingChatId')
    if not chat_id:
        return {'skipped': True, 'reason': 'no_chat_id'}

    text = _build_text(row)
    keyboard = build_hj_keyboard(
        sarang_id, settings.TG_CALLBACK_HMAC_SECRET, chat_id,
        row['has_replied'] == '1', row['is_window_opened'] == '1', row['approval_status'] or '',
    )

    outcome = None
    previous_msg_id = row['telegram_msg_id']
    if previous_msg_id:
        try:
            result = tel_router_client.enqueue(
                'editMessageText',
                {'chat_id': chat_id, 'message_id': previous_msg_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': keyboard},
                await_result=True,
            )
            if result.get('ok'):
                outcome = {'sent': True, 'edited': True, 'messageId': previous_msg_id}
            elif 'message is not modified' in str(result.get('description') or ''):
                outcome = {'sent': True, 'edited': False, 'noChange': True}
        except Exception:
            logger.warning('[habjaeyang] editMessageText failed, falling back to sendMessage', exc_info=True)

    if outcome is None:
        try:
            result = tel_router_client.enqueue(
                'sendMessage', {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML', 'reply_markup': keyboard}, await_result=True,
            )
            if not result.get('ok'):
                logger.warning('[habjaeyang] sendMessage rejected: %s', result.get('description'))
                outcome = {'sent': False}
            else:
                new_msg_id = result.get('result', {}).get('message_id')
                if new_msg_id:
                    client.exec(
                        "UPDATE SARANG_HAB_JAE_YANG SET TELEGRAM_MSG_ID = :1 WHERE HAB_JAE_YANG_ID = :2",
                        [str(new_msg_id), row['hab_jae_yang_id']],
                    )
                outcome = {'sent': True, 'edited': False, 'messageId': new_msg_id}
        except Exception:
            logger.warning('[habjaeyang] sendMessage failed', exc_info=True)
            outcome = {'sent': False}

    if refresh_dashboard:
        try:
            refresh_prospect_dashboard(client, row['team_id'], allow_create=True)
        except Exception:
            logger.warning('[habjaeyang] prospect dashboard refresh failed', exc_info=True)

    return outcome


def refresh_hj_markup(client, sarang_id, chat_id, message_id):
    """텔레그램 버튼(답장/창개설/재가) 탭 직후 — 전체 카드 재전송 없이 버튼만 갱신."""
    row = _fetch(client, sarang_id)
    if not row or not row['hab_jae_yang_id']:
        return
    keyboard = build_hj_keyboard(
        sarang_id, settings.TG_CALLBACK_HMAC_SECRET, chat_id,
        row['has_replied'] == '1', row['is_window_opened'] == '1', row['approval_status'] or '',
    )
    try:
        tel_router_client.enqueue(
            'editMessageReplyMarkup', {'chat_id': chat_id, 'message_id': message_id, 'reply_markup': keyboard},
        )
    except Exception:
        logger.warning('[habjaeyang] editMessageReplyMarkup failed', exc_info=True)

    try:
        refresh_prospect_dashboard(client, row['team_id'], allow_create=False)
    except Exception:
        logger.warning('[habjaeyang] prospect dashboard refresh failed', exc_info=True)
