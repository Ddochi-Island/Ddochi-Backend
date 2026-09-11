# BROADCAST_SETTINGS.CONFIG(TEAM_ID, BROADCAST_TYPE='prospect_chat') 조작 헬퍼 —
# services/main의 db/teamConfig.js 포팅. 텔레그램 chatId들과 팀별 설정을 한 행의
# JSON(CLOB)에 모아 담는다. team은 이 프로젝트에 TEAMS 테이블이 없어서
# MEMBER_AFFILIATION_HISTORIES.REGION_CODE 코드값을 그대로 씀(별도 resolve 불필요).
import json

BROADCAST_TYPE = 'prospect_chat'


def load_team_config(client, team_id):
    row = client.query_one(
        "SELECT CONFIG FROM BROADCAST_SETTINGS WHERE TEAM_ID = :1 AND BROADCAST_TYPE = :2 AND DELETED_AT IS NULL",
        [team_id, BROADCAST_TYPE],
    )
    if not row or not row.get('config'):
        return {}
    try:
        return json.loads(row['config'])
    except (TypeError, ValueError):
        return {}


def patch_team_config(client, team_id, patch, author):
    """patch 값이 None이면 그 키를 지움(연결 해제) — JSON_MERGEPATCH가 null 값을
    삭제로 처리함. CONFIG 전체를 덮지 않고 patch에 준 키만 병합하므로 동시에 다른
    채널을 설정 중이어도 서로 덮어쓰지 않음."""
    patch_json = json.dumps(patch)
    client.exec(
        """MERGE INTO BROADCAST_SETTINGS bs
           USING (SELECT :1 AS TEAM_ID, :2 AS BROADCAST_TYPE FROM dual) src
              ON (bs.TEAM_ID = src.TEAM_ID AND bs.BROADCAST_TYPE = src.BROADCAST_TYPE)
         WHEN MATCHED THEN UPDATE SET CONFIG = JSON_MERGEPATCH(NVL(CONFIG, '{}'), :3),
                UPDATED_AT = SYSTIMESTAMP, UPDATED_BY = :4
         WHEN NOT MATCHED THEN INSERT (TEAM_ID, BROADCAST_TYPE, ENABLED, BROADCAST_MODE, CONFIG, CREATED_BY, UPDATED_BY)
              VALUES (:5, :6, 1, 'event', :7, :8, :9)""",
        [team_id, BROADCAST_TYPE, patch_json, author, team_id, BROADCAST_TYPE, patch_json, author, author],
    )


def load_all_team_configs(client, team_ids):
    if not team_ids:
        return {}
    placeholders = ', '.join(f':{i + 1}' for i in range(len(team_ids)))
    rows = client.query(
        f"""SELECT TEAM_ID, CONFIG FROM BROADCAST_SETTINGS
             WHERE BROADCAST_TYPE = '{BROADCAST_TYPE}' AND TEAM_ID IN ({placeholders}) AND DELETED_AT IS NULL""",
        team_ids,
    )
    out = {}
    for r in rows:
        try:
            out[r['team_id']] = json.loads(r['config']) if r['config'] else {}
        except (TypeError, ValueError):
            out[r['team_id']] = {}
    return out
