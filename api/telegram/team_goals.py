# BROADCAST_SETTINGS.CONFIG(TEAM_ID, BROADCAST_TYPE='telegram_goals') 조작 헬퍼 —
# team_config.py와 동일한 CONFIG-JSON-머지 패턴, 단 이 BROADCAST_TYPE 전용.
# CONFIG shape: {[districtCode]: {talk,qr,promo,dm,reg,appr}, ...} — 구역별 목표를
# 팀 통계 메시지에서 합산해서 씀. 목표 입력 UI(GoalSettingModal.vue)는 stats.py의
# get/save_telegram_goals + teams.py의 get_team_areas로 연결(2026-09-30). 구역 키는 area_key() 형식.
import json

BROADCAST_TYPE = 'telegram_goals'
GOAL_KEYS = ('talk', 'appr', 'reg', 'promo', 'dm', 'qr')


def load_team_goal_total(client, region_code):
    row = client.query_one(
        "SELECT CONFIG FROM BROADCAST_SETTINGS WHERE TEAM_ID = :1 AND BROADCAST_TYPE = :2 AND DELETED_AT IS NULL",
        [region_code, BROADCAST_TYPE],
    )
    total = {k: 0 for k in GOAL_KEYS}
    if not row or not row.get('config'):
        return total
    try:
        raw = json.loads(row['config'])
    except (TypeError, ValueError):
        return total
    if not isinstance(raw, dict):
        return total
    for district_key, district_goals in raw.items():
        if district_key == 'Total' or not isinstance(district_goals, dict):
            continue
        for k in GOAL_KEYS:
            try:
                total[k] += int(district_goals.get(k) or 0)
            except (TypeError, ValueError):
                pass
    return total


def area_key(district_code):
    """목표 CONFIG의 구역 키 — 목표 설정 화면(get-team-areas)과 레거시 가져오기가 같은 형식을 쓰게."""
    return f'{district_code}구역'


def load_team_goals(client, region_code):
    row = client.query_one(
        "SELECT CONFIG FROM BROADCAST_SETTINGS WHERE TEAM_ID = :1 AND BROADCAST_TYPE = :2 AND DELETED_AT IS NULL",
        [region_code, BROADCAST_TYPE],
    )
    try:
        goals = json.loads(row['config']) if row and row.get('config') else {}
    except (TypeError, ValueError):
        goals = {}
    return goals if isinstance(goals, dict) else {}


def save_team_goals(client, region_code, goals, author):
    """CONFIG 전체를 교체(목표 설정 화면은 항상 전 구역 + Total을 한 번에 보냄)."""
    config = json.dumps(goals, ensure_ascii=False)
    client.exec(
        """MERGE INTO BROADCAST_SETTINGS bs
           USING (SELECT :1 AS TEAM_ID, :2 AS BROADCAST_TYPE FROM dual) src
              ON (bs.TEAM_ID = src.TEAM_ID AND bs.BROADCAST_TYPE = src.BROADCAST_TYPE)
         WHEN MATCHED THEN UPDATE SET CONFIG = :3, DELETED_AT = NULL, UPDATED_AT = SYSTIMESTAMP, UPDATED_BY = :4
         WHEN NOT MATCHED THEN INSERT (TEAM_ID, BROADCAST_TYPE, ENABLED, BROADCAST_MODE, CONFIG, CREATED_BY, UPDATED_BY)
              VALUES (:5, :6, 1, 'event', :7, :8, :9)""",
        [region_code, BROADCAST_TYPE, config, author, region_code, BROADCAST_TYPE, config, author, author],
    )
