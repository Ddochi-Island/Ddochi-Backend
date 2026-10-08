# 텔레그램 "/t 섭외자 교사", "/r 섭외자" — 섭외자 이름으로 그 방 지역의 매칭 건을 찾음(코드 대신 이름으로 쓰게)
import json

from django.utils import timezone

from api.telegram.team_config import BROADCAST_TYPE


def regions_for_chat(client, chat_id):
    """이 방이 연결된 지역들(지역 설정의 어떤 채널이든 이 chat_id면). 못 찾으면 None = 전 지역에서 찾음."""
    rows = client.query(
        "SELECT TEAM_ID, CONFIG FROM BROADCAST_SETTINGS WHERE BROADCAST_TYPE = :1 AND DELETED_AT IS NULL",
        [BROADCAST_TYPE],
    )
    out = []
    for r in rows:
        try:
            cfg = json.loads(r['config']) if r['config'] else {}
        except (TypeError, ValueError):
            continue
        if str(r['team_id']).isdigit() and any(
                k.endswith('ChatId') and str(v) == str(chat_id) for k, v in cfg.items()):
            out.append(r['team_id'])
    return out or None


def find_open_matches(client, name, chat_id, past_only=False):
    """이름이 같은 사랑이 중 결과 없는(열린) 매칭이 있는 건 — [{sarang_id, short, name, mt, guide}].
    지역은 매칭 현황판과 같은 기준(인도자 → 유입자 → 담당자 소속). past_only면 만남 시각이 지난 건만."""
    regions = regions_for_chat(client, chat_id)
    region_sql, args = '', [name.strip()]
    if regions:
        marks = ', '.join(f':{i + 2}' for i in range(len(regions)))
        region_sql = f'AND mah.REGION_CODE IN ({marks})'
        args += regions
    rows = client.query(
        f"""SELECT s.SARANG_ID, spi.NAME, gm.NAME AS GUIDE,
                   TO_CHAR(smh.MATCHED_AT, 'YYYY-MM-DD HH24:MI') AS MT
              FROM SARANG s
              JOIN SARANG_PERSONAL_INFO spi ON spi.PERSONAL_INFO_ID = s.PERSONAL_INFO_ID
              JOIN SARANG_MATCH_HISTORIES smh ON smh.SARANG_ID = s.SARANG_ID AND smh.RESULT IS NULL
              JOIN SARANG_HAB_JAE_YANG hj ON hj.SARANG_ID = s.SARANG_ID AND hj.IS_ACTIVE = 1
              LEFT JOIN MEMBERS gm ON gm.MEMBER_ID = hj.GUIDE_MEMBER_ID
              JOIN MEMBER_AFFILIATION_HISTORIES mah
                ON mah.MEMBER_ID = COALESCE(hj.GUIDE_MEMBER_ID,
                     (SELECT x.INTRODUCER_MEMBER_ID FROM SARANG_INFLOW_DETAILS x WHERE x.SARANG_ID = s.SARANG_ID),
                     s.INFLOW_MEMBER_ID) AND mah.IS_CURRENT = 1
             WHERE spi.NAME = :1 AND s.DELETED_AT IS NULL {region_sql}
             ORDER BY smh.MATCHED_AT""",
        args,
    )
    if past_only:
        now = timezone.localtime().strftime('%Y-%m-%d %H:%M')
        rows = [r for r in rows if r['mt'] and r['mt'] <= now]
    return [{'sarang_id': r['sarang_id'], 'short': r['sarang_id'][-8:].upper(), 'name': r['name'],
             'mt': (r['mt'] or '')[5:].replace('-', '/') or '날짜 미정', 'guide': r['guide'] or '-'} for r in rows]
