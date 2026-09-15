# adminUsers.js 포팅 — 사명의 길 "명단 관리" 화면. 레거시는 USERS/TEAMS/AREAS/ROLES
# 스키마였지만 이 프로젝트는 MEMBERS/MEMBER_AFFILIATION_HISTORIES/MEMBER_POSITION_
# MAPPINGS/POSITION_CODES로 재설계됨 — TEAMS/AREAS에 DISPLAY_NAME이 없어서 team_id/
# area_id를 이름 자리에도 그대로 씀(teams.py의 get_teams와 동일 관례).
import json
import re

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from api.auth.gate import require_jwt
from api.clients.data_router import DataRouterClient

_SABUN_RE = re.compile(r'^[a-zA-Z0-9_-]{1,20}$')
_SCOPE_ORDER = "CASE pc.SCOPE WHEN 'global' THEN 0 WHEN 'region' THEN 1 ELSE 2 END"
# 같은 트랜잭션에서 MEMBER_AFFILIATION_HISTORIES를 UPDATE(기존 행 닫기) 하고
# 바로 INSERT(새 행 열기) 하면 ORA-12838(parallel DML 후 재접근 금지)이 나서
# 트랜잭션 맨 앞에 붙여줌.
_DISABLE_PARALLEL_DML = {'sql': 'ALTER SESSION DISABLE PARALLEL DML', 'args': []}


def _json_body(request):
    try:
        return json.loads(request.body or b'{}')
    except (TypeError, ValueError):
        return {}


@csrf_exempt
@require_jwt
def admin_users_list(request, *args, **kwargs):
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    client = DataRouterClient()
    # 멤버당 상관 서브쿼리/JOIN+LISTAGG로 한 방에 집계하면 500명 스케일에서 dev ADB가
    # 8초 기본 타임아웃을 넘겨서, 단순 쿼리 두 번(멤버 목록 / 직책 매핑 전체)으로
    # 쪼개고 병합은 파이썬에서 함 — 둘 다 가볍고 빠름.
    rows = client.query(
        """SELECT m.MEMBER_ID AS SABUN, m.NAME, m.STATUS, m.GMAIL, m.TELEGRAM_ID,
                  mah.REGION_CODE AS TEAM_ID, mah.DISTRICT_CODE AS AREA_ID
             FROM MEMBERS m
             LEFT JOIN MEMBER_AFFILIATION_HISTORIES mah ON mah.MEMBER_ID = m.MEMBER_ID AND mah.IS_CURRENT = 1
            WHERE m.DELETED_AT IS NULL
            ORDER BY mah.REGION_CODE NULLS LAST, mah.DISTRICT_CODE NULLS LAST, m.NAME""",
    )
    pos_rows = client.query(
        f"""SELECT mpm.MEMBER_ID, mpm.POSITION_CODE, pc.POSITION_NAME
              FROM MEMBER_POSITION_MAPPINGS mpm
              JOIN POSITION_CODES pc ON pc.POSITION_CODE = mpm.POSITION_CODE AND pc.DELETED_AT IS NULL
             ORDER BY mpm.MEMBER_ID, {_SCOPE_ORDER}""",
    )
    by_member = {}
    for p in pos_rows:
        by_member.setdefault(p['member_id'], []).append((p['position_code'], p['position_name']))

    out = []
    for r in rows:
        positions = by_member.get(r['sabun'], [])
        out.append({
            'sabun': r['sabun'], 'name': r['name'], 'status': (r['status'] or 'ACTIVE').lower(),
            'team_id': r['team_id'], 'team_name': r['team_id'],
            'area_id': r['area_id'], 'area_name': r['area_id'],
            'gmail': r['gmail'], 'telegram_id': r['telegram_id'],
            'positions': ','.join(p[1] for p in positions) or None,
            'role_ids': ','.join(p[0] for p in positions) or None,
        })
    return JsonResponse({'success': True, 'list': out})


@csrf_exempt
@require_jwt
def admin_users_meta(request, *args, **kwargs):
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    client = DataRouterClient()
    team_rows = client.query(
        "SELECT DISTINCT REGION_CODE FROM MEMBER_AFFILIATION_HISTORIES WHERE IS_CURRENT = 1 ORDER BY REGION_CODE"
    )
    area_rows = client.query(
        """SELECT DISTINCT REGION_CODE, DISTRICT_CODE FROM MEMBER_AFFILIATION_HISTORIES
            WHERE IS_CURRENT = 1 ORDER BY REGION_CODE, DISTRICT_CODE"""
    )
    role_rows = client.query(
        f"SELECT POSITION_CODE, POSITION_NAME, SCOPE FROM POSITION_CODES pc WHERE DELETED_AT IS NULL ORDER BY {_SCOPE_ORDER}, POSITION_NAME"
    )
    return JsonResponse({
        'success': True,
        'teams': [{'team_id': r['region_code'], 'display_name': r['region_code']} for r in team_rows],
        'areas': [{'area_id': r['district_code'], 'team_id': r['region_code'], 'display_name': r['district_code']} for r in area_rows],
        'roles': [{'role_id': r['position_code'], 'name': r['position_name'], 'scope': r['scope']} for r in role_rows],
    })


def _role_stmts(sabun, role_ids):
    stmts = [{'sql': "DELETE FROM MEMBER_POSITION_MAPPINGS WHERE MEMBER_ID = :1", 'args': [sabun]}]
    for role_id in role_ids or []:
        stmts.append({
            'sql': "INSERT INTO MEMBER_POSITION_MAPPINGS (MEMBER_ID, POSITION_CODE, ASSIGNED_AT) VALUES (:1, :2, SYSDATE)",
            'args': [sabun, role_id],
        })
    return stmts


@csrf_exempt
@require_jwt
def admin_users_create(request, *args, **kwargs):
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    sabun = str(body.get('newSabun') or '').strip()
    name = str(body.get('name') or '').strip()
    team_id = str(body.get('teamId') or '').strip()
    area_id = str(body.get('areaId') or '').strip()
    if not sabun or not name or not team_id or not area_id:
        return JsonResponse({'success': False, 'message': '사번/이름/지역/구역은 필수야'}, status=400)
    if not _SABUN_RE.match(sabun):
        return JsonResponse({'success': False, 'message': '사번은 영문/숫자/_ - 20자 이내만 가능해'}, status=400)

    client = DataRouterClient()
    if client.query_one("SELECT 1 FROM MEMBERS WHERE MEMBER_ID = :1", [sabun]):
        return JsonResponse({'success': False, 'message': '이미 존재하는 사번이야'}, status=400)

    status = str(body.get('status') or 'active').upper()
    stmts = [{
        'sql': """INSERT INTO MEMBERS (MEMBER_ID, NAME, STATUS, GMAIL, TELEGRAM_ID, CREATED_BY, UPDATED_BY)
                  VALUES (:1, :2, :3, :4, :5, :6, :6)""",
        'args': [sabun, name, status, str(body.get('gmail') or '').strip() or None, str(body.get('telegramId') or '').strip() or None, request.user['sabun']],
    }, {
        'sql': """INSERT INTO MEMBER_AFFILIATION_HISTORIES (MEMBER_ID, REGION_CODE, DISTRICT_CODE, START_DATE, IS_CURRENT)
                  VALUES (:1, :2, :3, SYSDATE, 1)""",
        'args': [sabun, team_id, area_id],
    }] + _role_stmts(sabun, body.get('roleIds'))
    client.tx(stmts)
    return JsonResponse({'success': True, 'message': f'{name} 추가 완료'})


@csrf_exempt
@require_jwt
def admin_users_update(request, *args, **kwargs):
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    sabun = str(body.get('targetSabun') or '').strip()
    name = str(body.get('name') or '').strip()
    team_id = str(body.get('teamId') or '').strip()
    area_id = str(body.get('areaId') or '').strip()
    status = str(body.get('status') or '').strip()
    if not sabun or not name or not team_id or not area_id or not status:
        return JsonResponse({'success': False, 'message': '필수 항목 누락'}, status=400)

    client = DataRouterClient()
    cur = client.query_one(
        "SELECT REGION_CODE, DISTRICT_CODE FROM MEMBER_AFFILIATION_HISTORIES WHERE MEMBER_ID = :1 AND IS_CURRENT = 1",
        [sabun],
    )
    stmts = [{
        'sql': """UPDATE MEMBERS SET NAME = :1, STATUS = :2, GMAIL = :3, TELEGRAM_ID = :4,
                         UPDATED_AT = SYSTIMESTAMP, UPDATED_BY = :5
                   WHERE MEMBER_ID = :6 AND DELETED_AT IS NULL""",
        'args': [name, status.upper(), str(body.get('gmail') or '').strip() or None, str(body.get('telegramId') or '').strip() or None, request.user['sabun'], sabun],
    }]
    if not cur or cur['region_code'] != team_id or cur['district_code'] != area_id:
        # 소속 변경 — MEMBER_AFFILIATION_HISTORIES는 이력 테이블이라 기존 행을 닫고 새 행을 연다.
        if cur:
            stmts.insert(0, _DISABLE_PARALLEL_DML)
            stmts.append({
                'sql': "UPDATE MEMBER_AFFILIATION_HISTORIES SET IS_CURRENT = 0, END_DATE = SYSDATE WHERE MEMBER_ID = :1 AND IS_CURRENT = 1",
                'args': [sabun],
            })
        stmts.append({
            'sql': """INSERT INTO MEMBER_AFFILIATION_HISTORIES (MEMBER_ID, REGION_CODE, DISTRICT_CODE, START_DATE, IS_CURRENT)
                      VALUES (:1, :2, :3, SYSDATE, 1)""",
            'args': [sabun, team_id, area_id],
        })
    stmts += _role_stmts(sabun, body.get('roleIds'))
    client.tx(stmts)
    return JsonResponse({'success': True, 'message': f'{name} 수정 완료'})


@csrf_exempt
@require_jwt
def admin_users_bulk_update(request, *args, **kwargs):
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    sabuns = body.get('targetSabuns')
    change_type = str(body.get('type') or '')
    if not isinstance(sabuns, list) or not sabuns:
        return JsonResponse({'success': False, 'message': '대상 사번 목록이 없어'}, status=400)
    if change_type not in ('team', 'area', 'roles'):
        return JsonResponse({'success': False, 'message': '잘못된 변경 유형이야'}, status=400)

    client = DataRouterClient()
    team_id = str(body.get('teamId') or '').strip()
    area_id = str(body.get('areaId') or '').strip()
    for sabun in sabuns:
        if change_type == 'roles':
            client.tx(_role_stmts(sabun, body.get('roleIds')))
            continue
        cur = client.query_one(
            "SELECT REGION_CODE, DISTRICT_CODE FROM MEMBER_AFFILIATION_HISTORIES WHERE MEMBER_ID = :1 AND IS_CURRENT = 1",
            [sabun],
        )
        if change_type == 'team':
            new_region, new_district = team_id, (cur['district_code'] if cur else area_id)
        else:  # 'area' — teamId를 같이 보냈으면(다른 지역 구역으로 이동) 그걸 쓰고, 아니면 현재 지역 유지.
            new_region = team_id or (cur['region_code'] if cur else '')
            new_district = area_id
        stmts = []
        if cur:
            stmts.append(_DISABLE_PARALLEL_DML)
            stmts.append({
                'sql': "UPDATE MEMBER_AFFILIATION_HISTORIES SET IS_CURRENT = 0, END_DATE = SYSDATE WHERE MEMBER_ID = :1 AND IS_CURRENT = 1",
                'args': [sabun],
            })
        stmts.append({
            'sql': """INSERT INTO MEMBER_AFFILIATION_HISTORIES (MEMBER_ID, REGION_CODE, DISTRICT_CODE, START_DATE, IS_CURRENT)
                      VALUES (:1, :2, :3, SYSDATE, 1)""",
            'args': [sabun, new_region, new_district],
        })
        client.tx(stmts)

    label = {'team': '지역 이동', 'area': '구역 이동', 'roles': '직책 변경'}[change_type]
    return JsonResponse({'success': True, 'message': f'{len(sabuns)}명 {label} 완료'})


@csrf_exempt
@require_jwt
def admin_users_swap_teams(request, *args, **kwargs):
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    team_id1 = str(body.get('teamId1') or '').strip()
    team_id2 = str(body.get('teamId2') or '').strip()
    if not team_id1 or not team_id2 or team_id1 == team_id2:
        return JsonResponse({'success': False, 'message': '서로 다른 두 지역을 선택해줘'}, status=400)

    client = DataRouterClient()
    # 이 스키마엔 TEAMS.DISPLAY_NAME 같은 이름 테이블이 없어서(팀 코드 자체가 이름) —
    # 레거시처럼 이름을 바꾸는 게 아니라 두 지역 코드에 소속된 인원을 통째로 맞바꾼다.
    client.exec(
        """UPDATE MEMBER_AFFILIATION_HISTORIES
              SET REGION_CODE = CASE REGION_CODE WHEN :1 THEN :2 ELSE :1 END
            WHERE REGION_CODE IN (:1, :2) AND IS_CURRENT = 1""",
        [team_id1, team_id2],
    )
    # 텔레그램 방/목표 설정도 그대로 사람을 따라가도록 두 지역의 CONFIG를 교환.
    for broadcast_type in ('prospect_chat', 'telegram_goals'):
        cfg1 = client.query_one(
            "SELECT CONFIG FROM BROADCAST_SETTINGS WHERE TEAM_ID = :1 AND BROADCAST_TYPE = :2 AND DELETED_AT IS NULL",
            [team_id1, broadcast_type],
        )
        cfg2 = client.query_one(
            "SELECT CONFIG FROM BROADCAST_SETTINGS WHERE TEAM_ID = :1 AND BROADCAST_TYPE = :2 AND DELETED_AT IS NULL",
            [team_id2, broadcast_type],
        )
        for team_id, cfg in ((team_id1, cfg2), (team_id2, cfg1)):
            config_json = cfg['config'] if cfg else '{}'
            client.exec(
                """MERGE INTO BROADCAST_SETTINGS bs
                   USING (SELECT :1 AS TEAM_ID, :2 AS BROADCAST_TYPE FROM dual) src
                      ON (bs.TEAM_ID = src.TEAM_ID AND bs.BROADCAST_TYPE = src.BROADCAST_TYPE)
                 WHEN MATCHED THEN UPDATE SET CONFIG = :3, UPDATED_AT = SYSTIMESTAMP, UPDATED_BY = 'swapTeams'
                 WHEN NOT MATCHED THEN INSERT (TEAM_ID, BROADCAST_TYPE, ENABLED, BROADCAST_MODE, CONFIG, CREATED_BY, UPDATED_BY)
                      VALUES (:4, :5, 1, 'event', :6, 'swapTeams', 'swapTeams')""",
                [team_id, broadcast_type, config_json, team_id, broadcast_type, config_json],
            )
    return JsonResponse({'success': True, 'message': f'{team_id1} ↔ {team_id2} 스왑 완료'})
