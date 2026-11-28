# 교사 급구 — 오늘~3일 뒤 매칭 중 교사가 안 정해진 건을 "N지역 성별 N살 N시 장소 MBTI" 목록으로(2026-11-26)
import logging
import time

from django.utils import timezone

from api.telegram import tel_router_client
from api.telegram.dashboard_send import send_fresh_dashboard
from api.telegram.matching_dashboard import _fmt_md
from api.telegram.team_config import load_team_config, patch_team_config

logger = logging.getLogger('api.telegram.teacher_urgent')
TEAM_ID = '수지역'  # 교사 급구 방은 수지역 설정의 teacherUrgentChatId(텔레그램 연결 창 수지역 탭)

# 인도자가 이 직책이면 줄 앞에 🔫 (혁명특전대 — 사용자가 '혁명반'이라 부름)
_REVOLUTION_CODES = ('disp_special_forces', 'disp_special_forces_lead')
_CARD_GAP_S = 3.2


def fetch_rows(client):
    """교사 미정(합재양 교사·타지역 교사 둘 다 비어 있음)이고 결과 전인 매칭 시도 중 만남일이 오늘~3일 뒤인 것."""
    marks = ', '.join(f"'{c}'" for c in _REVOLUTION_CODES)
    return client.query(
        f"""SELECT s.SARANG_ID, s.GENDER, s.AGE, s.MBTI, mah.REGION_CODE AS REGION,
                  TO_CHAR(smh.MATCHED_AT, 'YYYY-MM-DD') AS MT_DATE, TO_CHAR(smh.MATCHED_AT, 'HH24:MI') AS MT_TIME,
                  smh.MATCH_LOCATION, hj.TELEGRAM_MSG_ID,
                  CASE WHEN EXISTS (SELECT 1 FROM MEMBER_POSITION_MAPPINGS p WHERE p.MEMBER_ID = hj.GUIDE_MEMBER_ID
                                     AND p.POSITION_CODE IN ({marks})) THEN 1 ELSE 0 END AS REVOLUTION
             FROM SARANG s
             JOIN SARANG_HAB_JAE_YANG hj ON hj.SARANG_ID = s.SARANG_ID AND hj.IS_ACTIVE = 1 AND hj.APPROVAL_STATUS = 'approved'
             JOIN SARANG_MATCH_HISTORIES smh ON smh.SARANG_ID = s.SARANG_ID AND smh.RESULT IS NULL
             JOIN MEMBER_AFFILIATION_HISTORIES mah ON mah.MEMBER_ID = hj.GUIDE_MEMBER_ID AND mah.IS_CURRENT = 1
            WHERE s.DELETED_AT IS NULL AND hj.TEACHER_MEMBER_ID IS NULL AND hj.TEACHER_NAME_OVERRIDE IS NULL
              AND smh.MATCHED_AT >= TRUNC(SYSDATE) AND smh.MATCHED_AT < TRUNC(SYSDATE) + INTERVAL '4' DAY
            ORDER BY smh.MATCHED_AT""",
        [],
    )


def _line(r):
    from api.views.erp import _norm_place  # erp가 views 쪽이라 호출 때 가져옴
    t = r['mt_time'] or ''
    when = f'{int(t[:2])}시' if t.endswith(':00') else t
    parts = [f"{r['region']}지역", r['gender'] or '', f"{r['age']}살" if r['age'] else '', when,
             _norm_place(r['match_location'].split('(')[0]) if r['match_location'] else '', (r['mbti'] or '').upper()]
    return ('🔫' if str(r['revolution']) == '1' else '') + ' '.join(p for p in parts if p)


def build_text(rows, links=None):
    """날짜별 ■ 묶음, 줄 아래 합재양 카드 링크(links: sarang_id → URL, 없으면 줄만)."""
    links = links or {}
    lines, day = ['🆘 교사 급구'], None
    for r in rows:
        if r['mt_date'] != day:
            day = r['mt_date']
            lines += ['', f'■ {_fmt_md(day)}']
        lines.append(_line(r))
        if links.get(r['sarang_id']):
            lines.append(links[r['sarang_id']])
            lines.append('')
    if len(lines) == 1:
        lines.append('\n교사가 필요한 매칭이 없어요 🎉')
    return '\n'.join(lines).rstrip()


def _msg_link(chat_id, msg_id):
    """비공개 그룹 메시지 링크 — chat_id -100xxxx → t.me/c/xxxx/<id>"""
    return f"https://t.me/c/{str(chat_id).removeprefix('-100')}/{msg_id}"


def _post_cards(client, chat_id, rows, posted):
    """카드가 아직 없는 사람의 합재양 카드를 올림 — posted(sarang_id → 메시지 id)를 채우고 (실패 사유, 보낸 게 있는지) 반환."""
    from api.telegram.habjaeyang import _build_text as card_text, _fetch as card_row  # 순환 import 회피

    sent_any, errors = False, []  # 카드 실패 사유 — 서버 로그를 못 봐서 설정에 남겨 확인(2026-11-28)
    for sid in dict.fromkeys(r['sarang_id'] for r in rows):
        if sid in posted:
            continue
        row = card_row(client, sid)
        if not row:
            continue
        # 그룹은 분당 20건 제한 — 몰아 보내면 429로 카드·목록이 빠져서(2026-11-28) 3초 간격으로
        if sent_any:
            time.sleep(_CARD_GAP_S)
        sent_any = True
        try:
            res = tel_router_client.enqueue('sendMessage', {'chat_id': chat_id, 'text': card_text(row), 'parse_mode': 'HTML'},
                                            await_result=True, timeout=60)
        except Exception as e:
            logger.warning('[teacher_urgent] card send failed', exc_info=True)
            errors.append(f'{sid[-8:]} {type(e).__name__}: {e}'[:200])
            continue
        if res.get('ok'):
            posted[sid] = res['result']['message_id']
        else:
            errors.append(f"{sid[-8:]} {res.get('error_code')} {res.get('description')}"[:200])
    return errors, sent_any


def _save_cards(client, rows, posted, errors):
    """지금 목록에 있는 사람만 남김 — 교사가 정해져 빠졌다가 다시 들어오면 카드를 새로 올림.
    JSON_MERGEPATCH는 객체를 병합하므로 빠진 사람은 null로 보내야 지워짐."""
    keep = {sid: posted[sid] for sid in dict.fromkeys(r['sarang_id'] for r in rows) if sid in posted}
    patch_team_config(client, TEAM_ID, {'teacherUrgentCards': {**{k: None for k in posted if k not in keep}, **keep},
                                        'teacherUrgentCardErrors': errors}, 'system')
    return keep


def send_teacher_urgent(client):
    """하루 3번(09·13·18시) — 목록에 있는 사람의 합재양 카드를 급구 방에 (처음 한 번만) 올리고, 카드 링크를 단 목록을 새 메시지로."""
    cfg = load_team_config(client, TEAM_ID)
    chat_id = cfg.get('teacherUrgentChatId')
    if not chat_id:
        return {'skipped': True, 'reason': 'no_chat_id'}
    rows = fetch_rows(client)
    posted = dict(cfg.get('teacherUrgentCards') or {})  # sarang_id → 카드 메시지 id
    errors, sent_any = _post_cards(client, chat_id, rows, posted)
    keep = _save_cards(client, rows, posted, errors)
    text = build_text(rows, {sid: _msg_link(chat_id, mid) for sid, mid in keep.items()})
    if sent_any:
        time.sleep(_CARD_GAP_S)
    return send_fresh_dashboard(client, TEAM_ID, chat_id, text, None, cfg, 'lastTeacherUrgentMsgId', 'lastTeacherUrgentMsgDate',
                                'teacher_urgent', no_link_preview=True)


def refresh_teacher_urgent(client):
    """교사·날짜·결과 입력 때 — 오늘 올린 목록을 그 자리에서 고침(교사 정해진 사람은 바로 빠짐, 2026-11-28).
    새로 들어온 사람은 카드도 바로 올려 링크를 닮."""
    cfg = load_team_config(client, TEAM_ID)
    chat_id, msg_id = cfg.get('teacherUrgentChatId'), cfg.get('lastTeacherUrgentMsgId')
    if not chat_id or not msg_id or cfg.get('lastTeacherUrgentMsgDate') != timezone.localdate().isoformat():
        return {'skipped': True}
    rows = fetch_rows(client)
    posted = dict(cfg.get('teacherUrgentCards') or {})
    errors, sent_any = _post_cards(client, chat_id, rows, posted)
    cards = _save_cards(client, rows, posted, errors) if sent_any else posted
    text = build_text(rows, {sid: _msg_link(chat_id, mid) for sid, mid in cards.items()})
    return tel_router_client.enqueue('editMessageText', {'chat_id': chat_id, 'message_id': msg_id, 'text': text,
                                                         'parse_mode': 'HTML', 'link_preview_options': {'is_disabled': True}})
