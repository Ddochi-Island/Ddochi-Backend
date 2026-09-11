"""teams.js 포팅 대상 — teams 라우트 스텁 (구조만, 로직은 미구현)."""
import json
import uuid

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from api.auth.gate import require_jwt
from api.clients.data_router import DataRouterClient


def _json_body(request):
    try:
        return json.loads(request.body or b'{}')
    except (TypeError, ValueError):
        return {}


@csrf_exempt
@require_jwt
def get_teams(request, *args, **kwargs):
    """섭외도구/경로 관리 화면의 팀 탭 + 팀 선택 드롭다운용. 이 프로젝트엔 TEAMS
    테이블이 없어서(REGIONS/TEAMS/AREAS 생략) MEMBER_AFFILIATION_HISTORIES에 실제
    쓰이고 있는 REGION_CODE 값들을 팀 코드로 그대로 씀 — DISPLAY_NAME 개념 없음."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    client = DataRouterClient()
    rows = client.query(
        """SELECT DISTINCT REGION_CODE FROM MEMBER_AFFILIATION_HISTORIES
            WHERE IS_CURRENT = 1 AND REGION_CODE IS NOT NULL
            ORDER BY REGION_CODE"""
    )
    codes = [r['region_code'] for r in rows]
    return JsonResponse({
        'success': True,
        'list': codes,
        'teams': [{'id': c, 'name': c} for c in codes],
    })


@csrf_exempt
def get_team_areas(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /get-team-areas 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def connect_telegram(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /connect-telegram 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
@require_jwt
def get_tool_configs(request, *args, **kwargs):
    """합재양 작성 폼의 "섭외도구" 드롭다운 + 도구 등록 관리 화면(ToolManagementModal) 목록."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    client = DataRouterClient()
    rows = client.query(
        """SELECT TOOL_CONFIG_ID, NAME, DESCRIPTION, CATEGORY, ORDER_KEY, AUTHOR_SABUN, TEAM_ID
             FROM TOOLS_CONFIGS WHERE DELETED_AT IS NULL ORDER BY ORDER_KEY, NAME"""
    )
    list_ = [{
        'id': r['tool_config_id'], 'toolName': r['name'], 'name': r['name'],
        'description': r['description'] or '', 'category': r['category'] or '',
        'sabun': r['author_sabun'], 'teamId': r['team_id'] or '', 'team': r['team_id'] or '',
        'order': int(r['order_key']),
    } for r in rows]
    return JsonResponse({'success': True, 'list': list_})


@csrf_exempt
@require_jwt
def save_tool_config(request, *args, **kwargs):
    """도구 등록/수정. 같은 이름이 이미 있으면(공용이든 팀 전용이든) 한 번 더
    확인시키고(name_conflict), force=true로 재요청하면 그대로 진행 — 프론트
    ToolManagementModal의 confirm-and-retry 흐름과 1:1."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    cfg = body.get('config') or {}
    name = str(cfg.get('toolName') or cfg.get('name') or '').strip()
    if not name:
        return JsonResponse({'success': False, 'message': 'name 필요'}, status=400)
    description = str(cfg.get('description') or '').strip()[:1000] or None
    category = str(cfg.get('category') or '').strip()[:50] or None
    team_raw = str(cfg.get('team') or '').strip()
    team_id = None if (not team_raw or team_raw == '전체') else team_raw.rstrip('팀')
    cfg_id = str(cfg.get('id') or '').strip() or None
    force = bool(body.get('force'))

    sabun = request.user['sabun']
    client = DataRouterClient()

    if not force:
        sql = "SELECT TOOL_CONFIG_ID, TEAM_ID FROM TOOLS_CONFIGS WHERE UPPER(TRIM(NAME)) = UPPER(:1) AND DELETED_AT IS NULL"
        args = [name]
        if cfg_id:
            sql += " AND TOOL_CONFIG_ID != :2"
            args.append(cfg_id)
        dup_rows = client.query(sql, args)
        if dup_rows:
            return JsonResponse({
                'success': False, 'code': 'name_conflict', 'message': '같은 이름의 도구가 이미 있어',
                'existing': [{
                    'id': r['tool_config_id'], 'teamId': r['team_id'] or None,
                    'teamLabel': (r['team_id'] + '팀') if r['team_id'] else '공용',
                } for r in dup_rows],
            })

    if cfg_id:
        affected = client.exec(
            """UPDATE TOOLS_CONFIGS SET NAME = :1, DESCRIPTION = :2, CATEGORY = :3, TEAM_ID = :4,
                   UPDATED_AT = SYSTIMESTAMP, UPDATED_BY = :5
                WHERE TOOL_CONFIG_ID = :6 AND DELETED_AT IS NULL""",
            [name, description, category, team_id, sabun, cfg_id],
        )
        if not affected:
            return JsonResponse({'success': False, 'message': '도구를 찾을 수 없어요'}, status=404)
        return JsonResponse({'success': True, 'message': '도구 수정 완료!'})

    new_id = f"tc_{uuid.uuid4().hex[:20]}"
    client.exec(
        """INSERT INTO TOOLS_CONFIGS (TOOL_CONFIG_ID, TEAM_ID, AUTHOR_SABUN, NAME, DESCRIPTION, CATEGORY, CREATED_BY, UPDATED_BY)
           VALUES (:1, :2, :3, :4, :5, :6, :7, :7)""",
        [new_id, team_id, sabun, name, description, category, sabun],
    )
    return JsonResponse({'success': True, 'message': '도구 등록 완료!', 'id': new_id})


@csrf_exempt
@require_jwt
def delete_tool_config(request, *args, **kwargs):
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    cfg_id = str(body.get('id') or '').strip()
    if not cfg_id:
        return JsonResponse({'success': False, 'message': 'id 필요'}, status=400)

    sabun = request.user['sabun']
    client = DataRouterClient()
    affected = client.exec(
        "UPDATE TOOLS_CONFIGS SET DELETED_AT = SYSTIMESTAMP, UPDATED_AT = SYSTIMESTAMP, UPDATED_BY = :1 WHERE TOOL_CONFIG_ID = :2 AND DELETED_AT IS NULL",
        [sabun, cfg_id],
    )
    if not affected:
        return JsonResponse({'success': False, 'message': '도구를 찾을 수 없어요'}, status=404)
    return JsonResponse({'success': True, 'message': '도구 삭제 완료!'})


@csrf_exempt
@require_jwt
def get_path_configs(request, *args, **kwargs):
    """합재양 작성 폼의 "섭외경로" 드롭다운 + 경로 관리 화면(PathManagementModal) 목록."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    client = DataRouterClient()
    rows = client.query(
        """SELECT PATH_CONFIG_ID, NAME, DESCRIPTION, ORDER_KEY, ON_OFF, AUTHOR_SABUN, TEAM_ID
             FROM PATH_CONFIGS WHERE DELETED_AT IS NULL ORDER BY ORDER_KEY, NAME"""
    )
    list_ = [{
        'id': r['path_config_id'], 'pathName': r['name'], 'name': r['name'],
        'description': r['description'] or '', 'onOff': r['on_off'] or 'online',
        'sabun': r['author_sabun'], 'teamId': r['team_id'] or '', 'team': r['team_id'] or '',
        'order': int(r['order_key']),
    } for r in rows]
    return JsonResponse({'success': True, 'list': list_})


@csrf_exempt
@require_jwt
def save_path_config(request, *args, **kwargs):
    """경로 등록/수정 — 관리 화면(PathManagementModal)에 팀 선택 UI가 없어서 항상
    공용(TEAM_ID NULL)으로 저장(레거시도 동일)."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    cfg = body.get('config') or {}
    name = str(cfg.get('pathName') or cfg.get('name') or '').strip()
    if not name:
        return JsonResponse({'success': False, 'message': 'name 필요'}, status=400)
    on_off = 'offline' if cfg.get('onOff') == 'offline' else 'online'
    cfg_id = str(cfg.get('id') or '').strip() or None

    sabun = request.user['sabun']
    client = DataRouterClient()

    if cfg_id:
        affected = client.exec(
            """UPDATE PATH_CONFIGS SET NAME = :1, ON_OFF = :2, UPDATED_AT = SYSTIMESTAMP, UPDATED_BY = :3
                WHERE PATH_CONFIG_ID = :4 AND DELETED_AT IS NULL""",
            [name, on_off, sabun, cfg_id],
        )
        if not affected:
            return JsonResponse({'success': False, 'message': '경로를 찾을 수 없어요'}, status=404)
        return JsonResponse({'success': True, 'message': '경로 수정 완료!'})

    new_id = f"pc_{uuid.uuid4().hex[:20]}"
    client.exec(
        """INSERT INTO PATH_CONFIGS (PATH_CONFIG_ID, AUTHOR_SABUN, NAME, ON_OFF, CREATED_BY, UPDATED_BY)
           VALUES (:1, :2, :3, :4, :5, :5)""",
        [new_id, sabun, name, on_off, sabun],
    )
    return JsonResponse({'success': True, 'message': '경로 등록 완료!', 'id': new_id})


@csrf_exempt
@require_jwt
def delete_path_config(request, *args, **kwargs):
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    cfg_id = str(body.get('id') or '').strip()
    if not cfg_id:
        return JsonResponse({'success': False, 'message': 'id 필요'}, status=400)

    sabun = request.user['sabun']
    client = DataRouterClient()
    affected = client.exec(
        "UPDATE PATH_CONFIGS SET DELETED_AT = SYSTIMESTAMP, UPDATED_AT = SYSTIMESTAMP, UPDATED_BY = :1 WHERE PATH_CONFIG_ID = :2 AND DELETED_AT IS NULL",
        [sabun, cfg_id],
    )
    if not affected:
        return JsonResponse({'success': False, 'message': '경로를 찾을 수 없어요'}, status=404)
    return JsonResponse({'success': True, 'message': '경로 삭제 완료!'})


@csrf_exempt
def get_return_home_config(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /get-return-home-config 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def save_return_home_config(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /save-return-home-config 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def get_auto_reject_config(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /get-auto-reject-config 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def save_auto_reject_config(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /save-auto-reject-config 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def team_setting_get(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /team-setting/get 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def team_setting_set(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /team-setting/set 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def save_activity_report_mode(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /save-activity-report-mode 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def link_telegram_user(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /link-telegram-user 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def get_team_cron_config(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /get-team-cron-config 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def set_team_cron_job(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /set-team-cron-job 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def get_scheduled_jobs(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /get-scheduled-jobs 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)


@csrf_exempt
def toggle_scheduled_job(request, *args, **kwargs):
    # TODO: services/main/src/routes/teams.js 의 POST /toggle-scheduled-job 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/teams.js"}, status=501)

