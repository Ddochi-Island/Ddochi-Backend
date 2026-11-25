# 텔레그램에서 매칭 결과 입력 — 매칭현황판의 "/r_<사랑이 뒤 8자리>" 명령 → 결과 버튼 → (사유 버튼 | 날짜 답장) → 저장.
# 교사 입력(/t_)과 같은 탭형 명령 + 합재양 카드와 같은 HMAC 버튼. 저장은 웹 결과입력과 같은 함수(record_*)를 씀.
import datetime
import html
import logging
import re

from django.conf import settings
from django.utils import timezone

from api.telegram import tel_router_client
from api.telegram.callback_hmac import sign_callback_data

logger = logging.getLogger('api.telegram.match_result_input')

ACTION = 'mr'
# 버튼 코드 → (라벨, 결과 코드). 콜백 데이터 64바이트 한도라 한 글자.
RESULTS = [('C', '취소', 'CANCEL'), ('D', '밀림', 'DELAY'), ('U', '비합', 'UNFIT'),
           ('X', '탈락', 'DROPOUT'), ('S', '2차만남', 'SECOND_MEET'), ('W', '상담연결', 'CONSULT_WIN')]
_RESULT_BY_CODE = {c: (label, rc) for c, label, rc in RESULTS}
# 사유가 필요한 결과 — 웹 결과입력(_RESULT_SUB_REASON_MAP)과 같은 사유
SUB_REASONS = {
    'C': [('경계취소', 'BOUNDARY_CANCEL'), ('갈부취소', 'CONFLICT_CANCEL'), ('환경취소', 'ENV_CANCEL'), ('연두취소', 'CONTACT_LOST_CANCEL')],
    'U': [('환경비합', 'ENV_UNFIT'), ('인성비합', 'PERSONALITY_UNFIT'), ('정신질환', 'MENTAL_HEALTH'), ('건강비합', 'HEALTH_UNFIT')],
    'X': [('경계탈락', 'BOUNDARY_DROPOUT'), ('갈부탈락', 'CONFLICT_DROPOUT')],
}
POSTPONE = {'D': '밀림처리', 'S': '2차만남'}
# 밀림 사유 — 밀림을 누르면 먼저 고르고(D1/D2) 그다음 날짜(2026-11-20). 웹 assets.DELAY_REASONS와 같은 순서
DELAY_REASONS = [('섭외자미룸', 'DELAY_RECRUIT_POSTPONE'), ('교사못구함', 'DELAY_NO_TEACHER')]
# 2026-11-25 결과 13개 목록 — 버튼 순서 그대로. 날짜가 필요한 건 (코드, 라벨), 바로 끝나는 건 E번호로 저장
SECOND_TERMS = [('단기', 'SECOND_SHORT'), ('장기', 'SECOND_LONG')]
ENDINGS = [('연락두절', 'CANCEL', 'CONTACT_LOST'), ('갈급부족', 'DROPOUT', 'LACK_OF_THIRST'), ('환경비합', 'UNFIT', 'ENV_UNFIT'),
           ('경계심', 'CANCEL', 'WARINESS'), ('중복섭외', 'CANCEL', 'DUPLICATE_RECRUIT'), ('정신질환', 'UNFIT', 'MENTAL_HEALTH'),
           ('인성비합', 'UNFIT', 'PERSONALITY_UNFIT'), ('병가', 'CANCEL', 'SICK_LEAVE')]
_E = {label: f'E{i + 1}' for i, (label, _, _) in enumerate(ENDINGS)}
FLAT = [('상담연결', 'W'), ('2차만남(단기)', 'S1'), ('2차만남(장기)', 'S2'), ('연락두절', _E['연락두절']), ('갈급부족', _E['갈급부족']),
        ('환경비합', _E['환경비합']), ('밀림(섭외자미룸)', 'D1'), ('밀림(교사못구함)', 'D2'), ('경계심', _E['경계심']),
        ('중복섭외', _E['중복섭외']), ('정신질환', _E['정신질환']), ('인성비합', _E['인성비합']), ('병가', _E['병가'])]
# 날짜 안내 메시지에 박는 꼬리표 — 답장이 오면 tel_router가 이걸로 어느 건인지 알아냄(상태 저장 없이).
# 밀림은 사유 번호까지(D1/D2), 사유 없는 D는 이 변경 전에 보낸 안내 메시지
DATE_TAG_RE = re.compile(r'#r_([0-9A-Fa-f]{8})([DS]\d?)')


def parse_kind(kind):
    """'D'/'S'/'D1'/'D2'/'S1'/'S2' → (POSTPONE 키, 밀림 사유·2차 단기/장기 (라벨, 코드) 또는 None). 모르는 값이면 None."""
    kind = str(kind or '')
    if kind in POSTPONE:
        return kind, None
    reasons = {'D': DELAY_REASONS, 'S': SECOND_TERMS}.get(kind[:1])
    if reasons and len(kind) == 2 and kind[1].isdigit() and 1 <= int(kind[1]) <= len(reasons):
        return kind[0], reasons[int(kind[1]) - 1]
    return None


def _cb(chat_id, short, code):
    return sign_callback_data(settings.TG_CALLBACK_HMAC_SECRET, ACTION, f'{short}.{code}', chat_id)


def _find_open(client, short):
    """뒤 8자리로 사랑이 + 열린(결과 없는) 매칭 시도. 없으면 None."""
    return client.query_one(
        """SELECT s.SARANG_ID, spi.NAME,
                  TO_CHAR(smh.MATCHED_AT, 'MM/DD HH24:MI') AS MT
             FROM SARANG s
             JOIN SARANG_PERSONAL_INFO spi ON spi.PERSONAL_INFO_ID = s.PERSONAL_INFO_ID
             JOIN SARANG_MATCH_HISTORIES smh ON smh.SARANG_ID = s.SARANG_ID AND smh.RESULT IS NULL
            WHERE UPPER(SUBSTR(s.SARANG_ID, -8)) = UPPER(:1) AND s.DELETED_AT IS NULL
            ORDER BY smh.MATCH_DEGREE DESC, smh.ATTEMPT_COUNT DESC
            FETCH FIRST 1 ROWS ONLY""",
        [short],
    )


def _head(row):
    return f"🛡️ <b>{html.escape(row['name'] or '-')}</b> 매칭 결과" + (f" ({row['mt']})" if row['mt'] else '')


def _result_keyboard(chat_id, short):
    btns = [{'text': label, 'callback_data': _cb(chat_id, short, c)} for label, c in FLAT]
    return {'inline_keyboard': [btns[i:i + 2] for i in range(0, len(btns), 2)]}


def _send(chat_id, text, markup=None, reply_to=None):
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
    if markup is not None:
        payload['reply_markup'] = markup
    if reply_to is not None:
        payload['reply_to_message_id'] = reply_to
    tel_router_client.enqueue('sendMessage', payload)


def _edit(chat_id, message_id, text, markup=None):
    tel_router_client.enqueue('editMessageText', {
        'chat_id': chat_id, 'message_id': message_id, 'text': text, 'parse_mode': 'HTML',
        'reply_markup': markup or {'inline_keyboard': []},
    })


def start(client, short, chat_id, reply_to=None):
    """/r_ 명령 — 결과 고르는 버튼 메시지를 보냄."""
    row = _find_open(client, short)
    if not row:
        _send(chat_id, '⚠️ 결과를 넣을 매칭 일정을 못 찾았어(이미 입력됐거나 잘못된 링크일 수 있어)', reply_to=reply_to)
        return
    _send(chat_id, _head(row) + '\n결과를 골라줘', _result_keyboard(chat_id, short.upper()), reply_to)


def handle_callback(client, args, chat_id, message_id, actor_resolver):
    """버튼 탭. args = '<short>.<code>' — code: 상담연결 W, 2차 단기/장기 S1/S2, 밀림 D1/D2, 끝(E1~E8), 미정(S10/S20/D10/D20), 뒤로(b).
    옛 버튼(C/U/X·C1/U2…·D·S·S0)도 그대로 받음."""
    from api.views.assets import MET_ASK, met_result, record_match_result, record_postpone  # 순환 import 회피

    short, _, code = str(args or '').partition('.')
    row = _find_open(client, short)
    if not row:
        _edit(chat_id, message_id, '⚠️ 이미 결과가 들어갔거나 일정이 없어')
        return {'toast': '이미 처리됐어'}
    head = _head(row)

    if code == 'b':
        _edit(chat_id, message_id, head + '\n결과를 골라줘', _result_keyboard(chat_id, short))
        return {'toast': None}

    if code == 'W':
        record_match_result(client, row['sarang_id'], 'CONSULT_WIN', None)
        _edit(chat_id, message_id, f'✅ {head}\n→ 상담연결 입력 완료')
        return {'toast': '상담연결 입력 완료'}

    ending = re.fullmatch(r'E(\d+)([mn]?)', code)
    if ending and 1 <= int(ending[1]) <= len(ENDINGS):
        label, result, sub = ENDINGS[int(ending[1]) - 1]
        if label in MET_ASK and not ending[2]:  # 경계심·중복섭외·정신질환·인성비합은 만났는지 먼저(2026-11-25) — ⭕️/❌ 구분
            back = {'text': '← 뒤로', 'callback_data': _cb(chat_id, short, 'b')}
            btns = [{'text': '만났어 ⭕️', 'callback_data': _cb(chat_id, short, f'{code}m')},
                    {'text': '안 만났어 ❌', 'callback_data': _cb(chat_id, short, f'{code}n')}]
            _edit(chat_id, message_id, f'{head}\n{label} — 섭외자를 만났어?', {'inline_keyboard': [btns, [back]]})
            return {'toast': None}
        if ending[2]:
            result, sub = met_result(label, ending[2] == 'm')
        record_match_result(client, row['sarang_id'], result, sub)
        shown = label + {'m': '(만남)', 'n': '(안 만남)'}.get(ending[2], '')
        _edit(chat_id, message_id, f'✅ {head}\n→ {shown} 입력 완료')
        return {'toast': f'{shown} 입력 완료'}

    if code in SUB_REASONS:  # 사유 고르기 — 13개 목록 전에 보낸 버튼(C/U/X)
        back = {'text': '← 뒤로', 'callback_data': _cb(chat_id, short, 'b')}
        btns = [{'text': label, 'callback_data': _cb(chat_id, short, f'{code}{i + 1}')} for i, (label, _) in enumerate(SUB_REASONS[code])]
        rows = [btns[i:i + 2] for i in range(0, len(btns), 2)] + [[back]]
        _edit(chat_id, message_id, f"{head}\n{_RESULT_BY_CODE[code][0]} 사유를 골라줘", {'inline_keyboard': rows})
        return {'toast': None}

    if len(code) >= 2 and code[0] in SUB_REASONS and code[1:].isdigit():
        reasons = SUB_REASONS[code[0]]
        idx = int(code[1:]) - 1
        if not 0 <= idx < len(reasons):
            return {'toast': '⚠️ 알 수 없는 사유'}
        label, sub = reasons[idx]
        record_match_result(client, row['sarang_id'], _RESULT_BY_CODE[code[0]][1], sub)
        _edit(chat_id, message_id, f'✅ {head}\n→ {label} 입력 완료')
        return {'toast': f'{label} 입력 완료'}

    if code == 'D':  # 밀림 — 사유 먼저
        back = {'text': '← 뒤로', 'callback_data': _cb(chat_id, short, 'b')}
        btns = [{'text': label, 'callback_data': _cb(chat_id, short, f'D{i + 1}')} for i, (label, _) in enumerate(DELAY_REASONS)]
        _edit(chat_id, message_id, f'{head}\n밀림 사유를 골라줘', {'inline_keyboard': [btns, [back]]})
        return {'toast': None}

    kind = parse_kind(code)
    if kind:  # 날짜 안내(2차만남 S, 밀림 사유 고른 뒤 D1/D2) — 답장으로 받음
        back = {'text': '← 뒤로', 'callback_data': _cb(chat_id, short, 'b')}
        undecided = {'text': '날짜 미정', 'callback_data': _cb(chat_id, short, f'{code}0')}
        label = _RESULT_BY_CODE[kind[0]][0] + (f'({kind[1][0]})' if kind[1] else '')
        _edit(chat_id, message_id,
              f"{head}\n{label} — 다음 만남 날짜를 <b>이 메시지에 답장</b>으로 보내줘\n예) <code>10/12 19:00</code>\n#r_{short}{code}",
              {'inline_keyboard': [[undecided, back]]})
        return {'toast': '날짜를 답장으로 보내줘'}

    if code.endswith('0') and parse_kind(code[:-1]):  # 날짜 미정(S0, D10/D20, 옛 버튼 D0)
        base, reason = parse_kind(code[:-1])
        actor = actor_resolver(client, row['sarang_id'])
        record_postpone(client, row['sarang_id'], POSTPONE[base], '미정', actor, sub_reason=reason[1] if reason else None)
        label = _RESULT_BY_CODE[base][0] + (f'({reason[0]})' if reason else '')
        _edit(chat_id, message_id, f'✅ {head}\n→ {label} (날짜 미정) 입력 완료')
        return {'toast': '입력 완료'}

    return {'toast': '⚠️ 알 수 없는 버튼'}


def parse_date(text, today=None):
    """'10/12 19:00', '10.12 7:30', '10-12 19시' → 'YYYY-MM-DD HH:MM'. 올해 기준, 한 달 넘게 지난 날짜면 내년. 못 읽으면 None."""
    m = re.search(r'(\d{1,2})\s*[/.\-월]\s*(\d{1,2})\s*일?\s+(\d{1,2})\s*(?::|시)\s*(\d{1,2})?', str(text or ''))
    if not m:
        return None
    mo, d, h, mi = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4) or 0)
    today = today or timezone.localdate()
    try:
        dt = datetime.datetime(today.year, mo, d, h, mi)
        if dt.date() < today - datetime.timedelta(days=30):
            dt = dt.replace(year=today.year + 1)
    except ValueError:
        return None
    return dt.strftime('%Y-%m-%d %H:%M')


def handle_date_reply(client, short, kind, text, chat_id, reply_to, prompt_message_id, actor_resolver):
    """날짜 안내 메시지에 단 답장 — 밀림/2차만남 저장."""
    from api.views.assets import record_postpone

    row = _find_open(client, short)
    if not row:
        _send(chat_id, '⚠️ 이미 결과가 들어갔거나 일정이 없어', reply_to=reply_to)
        return
    when = parse_date(text)
    if not when:
        _send(chat_id, '⚠️ 날짜를 못 읽었어. <code>10/12 19:00</code>처럼 보내줘', reply_to=reply_to)
        return
    base, reason = parse_kind(kind)
    label = _RESULT_BY_CODE[base][0] + (f'({reason[0]})' if reason else '')
    record_postpone(client, row['sarang_id'], POSTPONE[base], when, actor_resolver(client, row['sarang_id']),
                    sub_reason=reason[1] if reason else None)
    done = f"✅ {_head(row)}\n→ {label} ({when[5:].replace('-', '/')}) 입력 완료"
    if prompt_message_id:
        _edit(chat_id, prompt_message_id, done)
    _send(chat_id, done, reply_to=reply_to)
