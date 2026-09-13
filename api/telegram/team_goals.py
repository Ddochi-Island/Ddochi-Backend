# BROADCAST_SETTINGS.CONFIG(TEAM_ID, BROADCAST_TYPE='telegram_goals') 조작 헬퍼 —
# team_config.py와 동일한 CONFIG-JSON-머지 패턴, 단 이 BROADCAST_TYPE 전용.
# CONFIG shape: {[districtCode]: {talk,qr,promo,dm,reg,appr}, ...} — 구역별 목표를
# 팀 통계 메시지에서 합산해서 씀. 목표 입력 UI(GoalSettingModal.vue) 자체는
# stats.py의 save_telegram_goals/get_telegram_goals가 아직 501 스텁이라 미연결 —
# 값 없으면 그냥 0/목표없음으로 처리됨(team_stats.py의 bar()가 처리).
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
