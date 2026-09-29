"""dailyReport.js 포팅 대상 — daily_report 라우트 스텁 (구조만, 로직은 미구현).
daily_report/daily_report_get/daily_report_list_names/daily_report_reflections만 실제 구현 — 나머지(주간
계획/plan-execution 등)는 별개의 "일일 계획" 서브시스템이라 범위 밖."""
import datetime
import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from api.auth.gate import get_author_context, require_jwt
from api.clients.data_router import DataRouterClient, DataRouterError
from api.util.business_date import get_business_date
from api.views.assets import _member_id_by_name

logger = logging.getLogger('api.views.daily_report')

# 프론트(DailyReportScreen.vue)의 <select> 옵션은 값 자체가 한글 문구라 그대로
# 저장하려 하면 DAILY_REPORTS.ACTIVITY CHECK 제약(none/online/offline/offlineSearch)에
# 매번 위반됨 — 2026-09-25 실사용자 신고로 발견(제출할 때마다 500 나고 있었음,
# 이 화면이 사실상 한 번도 정상 동작한 적 없었던 것으로 보임). 프론트는 안 건드리고
# 여기서 왕복 변환.
_ACTIVITY_KO_TO_CODE = {
    '활동을 하지 못했어..': 'none',
    '비대면 활동!': 'online',
    '대면 활동!': 'offline',
    '오프찾 했어!': 'offlineSearch',
}
_ACTIVITY_CODE_TO_KO = {v: k for k, v in _ACTIVITY_KO_TO_CODE.items()}


def _json_body(request):
    try:
        return json.loads(request.body or b'{}')
    except (TypeError, ValueError):
        return {}


@csrf_exempt
@require_jwt
def daily_report_list_names(request, *args, **kwargs):
    """보고 대상자 autocomplete 명단 — 작성자와 같은 지역 소속 전원 + 이미 그
    dateKey에 보고서를 낸 다른 지역 사람(지역장 대리 제출 등 케이스 커버)."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    date_key = str(body.get('dateKey') or '').strip() or get_business_date()

    client = DataRouterClient()
    ctx = get_author_context(request.user['sabun'])
    rows = client.query(
        """SELECT DISTINCT m.NAME
             FROM MEMBERS m
             LEFT JOIN MEMBER_AFFILIATION_HISTORIES mah
               ON mah.MEMBER_ID = m.MEMBER_ID AND mah.IS_CURRENT = 1
             LEFT JOIN DAILY_REPORTS dr
               ON dr.MEMBER_ID = m.MEMBER_ID AND dr.REPORT_DATE = TO_DATE(:1, 'YYYY-MM-DD')
            WHERE m.DELETED_AT IS NULL
              AND (mah.REGION_CODE = :2 OR dr.MEMBER_ID IS NOT NULL)
            ORDER BY m.NAME""",
        [date_key, ctx['team_id']],
    )
    return JsonResponse({'success': True, 'names': [{'name': r['name']} for r in rows]})


@csrf_exempt
@require_jwt
def daily_report_get(request, *args, **kwargs):
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    date_key = str(body.get('dateKey') or body.get('date') or '').strip() or get_business_date()
    name = str(body.get('name') or '').strip()
    if not name:
        return JsonResponse({'success': False, 'message': 'name 필요'}, status=400)

    client = DataRouterClient()
    member_id = _member_id_by_name(client, name)
    if not member_id:
        return JsonResponse({'success': True, 'exists': False, 'data': None})

    row = client.query_one(
        """SELECT ACTIVITY, TALK_COUNT, DM_COUNT, QR_COUNT, ONLINE_INTAKE_COUNT,
                  PROMO_LIST, REG_LIST, IS_FINAL, SUBMITTED_AT, MOOD, REFLECTION
             FROM DAILY_REPORTS WHERE REPORT_DATE = TO_DATE(:1, 'YYYY-MM-DD') AND MEMBER_ID = :2""",
        [date_key, member_id],
    )
    if not row:
        return JsonResponse({'success': True, 'exists': False, 'data': None})

    try:
        reg_list = json.loads(row['reg_list']) if row['reg_list'] else []
    except (TypeError, ValueError):
        reg_list = []
    return JsonResponse({
        'success': True, 'exists': True,
        'data': {
            'activity': _ACTIVITY_CODE_TO_KO.get(row['activity'], row['activity']),
            'talkCount': int(row['talk_count'] or 0),
            'dmCount': int(row['dm_count'] or 0),
            'qrCount': int(row['qr_count'] or 0),
            'onlineIntakeCount': int(row['online_intake_count'] or 0),
            'promoList': row['promo_list'] or '',
            'regList': reg_list,
            'isFinal': row['is_final'] == '1',
            'submittedAt': row['submitted_at'],
            'mood': int(row['mood']) if row['mood'] else None,
            'reflection': row['reflection'] or '',
        },
    })


@csrf_exempt
@require_jwt
def daily_report(request, *args, **kwargs):
    # 처리 안 된 예외는 Django 기본 HTML 500이 되고, 프론트 callApi가 그걸 {}로 삼켜서 사용자한텐
    # 내용 없는 알림창만 뜸(2026-09-25, 09-28 제보) — 원인을 화면과 로그에 남기려고 여기서 한 번에 받음.
    try:
        return _daily_report(request)
    except Exception as e:
        logger.exception('[daily_report] unexpected error')
        return JsonResponse({'success': False, 'message': f'저장 실패: {type(e).__name__}: {e}'}, status=500)


def _daily_report(request):
    """일일보고 제출(upsert) — 제출 성공 후 그 사람 소속 지역의 일일보고 텔레그램
    메시지를 갱신(기존 메시지 있을 때만 edit, 없으면 조용히 skip — 새로 만드는 건
    정각 크론 몫)."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    name = str(body.get('name') or '').strip()
    date_key = str(body.get('dateKey') or body.get('confirmedDateKey') or '').strip() or get_business_date()
    activity_raw = str(body.get('activity') or '').strip()
    activity = _ACTIVITY_KO_TO_CODE.get(activity_raw, activity_raw) or 'none'
    if not name:
        return JsonResponse({'success': False, 'message': 'name 필요'}, status=400)

    client = DataRouterClient()
    member_id = _member_id_by_name(client, name)
    if not member_id:
        return JsonResponse({'success': False, 'message': f'[{name}]을(를) 명단에서 찾을 수 없어'}, status=404)

    target_ctx = get_author_context(member_id)
    author_sabun = request.user['sabun']

    def _int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

    reg_list_json = json.dumps(body.get('regList') or [])
    mood = _int(body.get('mood'))
    mood = mood if 1 <= mood <= 10 else None
    reflection = str(body.get('reflection') or '').strip() or None

    try:
        vals = [
            author_sabun, activity, _int(body.get('talkCount')), _int(body.get('dmCount')),
            _int(body.get('qrCount')), _int(body.get('onlineIntakeCount')), str(body.get('promoList') or ''), reg_list_json,
            1 if body.get('isFinal') else 0, target_ctx['team_id'], target_ctx['area_id'], mood, reflection,
        ]
        client.exec(
            """MERGE INTO DAILY_REPORTS dr
               USING (SELECT TO_DATE(:1, 'YYYY-MM-DD') AS REPORT_DATE, :2 AS MEMBER_ID FROM dual) src
                  ON (dr.REPORT_DATE = src.REPORT_DATE AND dr.MEMBER_ID = src.MEMBER_ID)
             WHEN MATCHED THEN UPDATE SET
                    AUTHOR_MEMBER_ID = :3, ACTIVITY = :4, TALK_COUNT = :5, DM_COUNT = :6,
                    QR_COUNT = :7, ONLINE_INTAKE_COUNT = :8, PROMO_LIST = :9, REG_LIST = :10,
                    IS_FINAL = :11, SNAP_REGION_CODE = :12, SNAP_DISTRICT_CODE = :13, MOOD = :14, REFLECTION = :15,
                    SUBMITTED_AT = SYSTIMESTAMP, UPDATED_AT = SYSTIMESTAMP, UPDATED_BY = :16
             WHEN NOT MATCHED THEN INSERT
                    (REPORT_DATE, MEMBER_ID, AUTHOR_MEMBER_ID, ACTIVITY, TALK_COUNT, DM_COUNT,
                     QR_COUNT, ONLINE_INTAKE_COUNT, PROMO_LIST, REG_LIST, IS_FINAL,
                     SNAP_REGION_CODE, SNAP_DISTRICT_CODE, MOOD, REFLECTION, CREATED_BY, UPDATED_BY)
                  VALUES (TO_DATE(:17, 'YYYY-MM-DD'), :18, :19, :20, :21, :22,
                          :23, :24, :25, :26, :27, :28, :29, :30, :31, :32, :33)""",
            [date_key, member_id, *vals, author_sabun,
             date_key, member_id, *vals, author_sabun, author_sabun],
        )
    except DataRouterError as e:
        logger.warning('[daily_report] MERGE failed: %s', e)
        return JsonResponse({'success': False, 'message': f'저장 실패: {e}'}, status=500)

    if target_ctx['team_id'] and target_ctx['team_id'] != '0':
        try:
            from api.telegram.team_stats import refresh_team_stats
            refresh_team_stats(client, target_ctx['team_id'], date_key)
        except Exception:
            logger.warning('[daily_report] team stats refresh failed', exc_info=True)

    return JsonResponse({'success': True, 'message': '🌰 보고 완료!'})


@csrf_exempt
def daily_report_search_reg(request, *args, **kwargs):
    # TODO: services/main/src/routes/dailyReport.js 의 POST /daily-report/search-reg 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dailyReport.js"}, status=501)


@csrf_exempt
def daily_report_add_reg_entry(request, *args, **kwargs):
    # TODO: services/main/src/routes/dailyReport.js 의 POST /daily-report/add-reg-entry 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dailyReport.js"}, status=501)


@csrf_exempt
def get_my_plan(request, *args, **kwargs):
    # TODO: services/main/src/routes/dailyReport.js 의 POST /get-my-plan 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dailyReport.js"}, status=501)


@csrf_exempt
def update_today_plan(request, *args, **kwargs):
    # TODO: services/main/src/routes/dailyReport.js 의 POST /update-today-plan 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dailyReport.js"}, status=501)


@csrf_exempt
def get_missed_executions(request, *args, **kwargs):
    # TODO: services/main/src/routes/dailyReport.js 의 POST /get-missed-executions 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dailyReport.js"}, status=501)


@csrf_exempt
def get_plan_execution(request, *args, **kwargs):
    # TODO: services/main/src/routes/dailyReport.js 의 POST /get-plan-execution 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dailyReport.js"}, status=501)


@csrf_exempt
def update_plan_execution(request, *args, **kwargs):
    # TODO: services/main/src/routes/dailyReport.js 의 POST /update-plan-execution 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dailyReport.js"}, status=501)


@csrf_exempt
def batch_update_executions(request, *args, **kwargs):
    # TODO: services/main/src/routes/dailyReport.js 의 POST /batch-update-executions 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dailyReport.js"}, status=501)


@csrf_exempt
def weekly_template_get(request, *args, **kwargs):
    # TODO: services/main/src/routes/dailyReport.js 의 POST /weekly-template/get 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dailyReport.js"}, status=501)


@csrf_exempt
def weekly_template_save_all(request, *args, **kwargs):
    # TODO: services/main/src/routes/dailyReport.js 의 POST /weekly-template/save-all 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dailyReport.js"}, status=501)


@csrf_exempt
def get_audit_logs(request, *args, **kwargs):
    # TODO: services/main/src/routes/dailyReport.js 의 POST /get-audit-logs 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dailyReport.js"}, status=501)


# 느낀점 열람은 팀장급 이상만(레거시 dailyReport.js:851 isAdminUser/hasRegionRole/hasTeamRole 미러) —
# 전역/지역 직책은 전 지역, 팀 직책(지역장/전도팀장/지역부서기/지역부전서)은 자기 지역만.
_REFLECTION_TEAM_POSITIONS = {'team_lead', 'team_evangelist', 'team_clerk', 'team_mission_clerk'}


@csrf_exempt
@require_jwt
def daily_report_reflections(request, *args, **kwargs):
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    client = DataRouterClient()
    viewer = client.query_one(
        """SELECT mah.REGION_CODE, mpm.POSITION_CODE, pc.SCOPE
             FROM MEMBERS m
             LEFT JOIN MEMBER_AFFILIATION_HISTORIES mah ON mah.MEMBER_ID = m.MEMBER_ID AND mah.IS_CURRENT = 1
             LEFT JOIN MEMBER_POSITION_MAPPINGS mpm ON mpm.MEMBER_ID = m.MEMBER_ID
             LEFT JOIN POSITION_CODES pc ON pc.POSITION_CODE = mpm.POSITION_CODE
            WHERE m.MEMBER_ID = :1
            ORDER BY CASE pc.SCOPE WHEN 'global' THEN 0 WHEN 'region' THEN 1 ELSE 2 END
            FETCH FIRST 1 ROWS ONLY""",
        [request.user['sabun']],
    ) or {}
    if viewer.get('scope') in ('global', 'region'):
        scope = 'all'
    elif viewer.get('position_code') in _REFLECTION_TEAM_POSITIONS:
        scope = 'team'
    else:
        return JsonResponse({'success': False, 'message': '권한이 없어 — 팀장급 이상만 조회 가능'}, status=403)

    body = _json_body(request)
    if scope == 'team':
        team_filter = viewer.get('region_code') or '__none__'
    else:
        team_filter = str(body.get('teamId') or '').strip() or None

    date_to = str(body.get('dateTo') or '').strip() or get_business_date()
    date_from = str(body.get('dateFrom') or '').strip() or (
        datetime.date.fromisoformat(date_to) - datetime.timedelta(days=13)).isoformat()

    sql = """SELECT TO_CHAR(dr.REPORT_DATE, 'YYYY-MM-DD') AS REPORT_DATE, dr.MEMBER_ID, dr.REFLECTION, dr.MOOD,
                    dr.SNAP_REGION_CODE, m.NAME AS USER_NAME, dr.SUBMITTED_AT
               FROM DAILY_REPORTS dr
               JOIN MEMBERS m ON m.MEMBER_ID = dr.MEMBER_ID
              WHERE dr.REPORT_DATE >= TO_DATE(:1, 'YYYY-MM-DD') AND dr.REPORT_DATE <= TO_DATE(:2, 'YYYY-MM-DD')
                AND dr.REFLECTION IS NOT NULL AND dr.DELETED_AT IS NULL"""
    args = [date_from, date_to]
    if team_filter:
        sql += " AND dr.SNAP_REGION_CODE = :3"
        args.append(team_filter)
    sql += " ORDER BY dr.REPORT_DATE DESC, dr.SUBMITTED_AT DESC"
    rows = client.query(sql, args, fetch_limit=5000)

    items = [{
        'date': r['report_date'], 'sabun': r['member_id'], 'name': r['user_name'],
        'teamId': r['snap_region_code'], 'teamName': f"{r['snap_region_code']}지역" if r['snap_region_code'] else '',
        'mood': int(r['mood']) if r['mood'] else None, 'reflection': r['reflection'],
        'submittedAt': r['submitted_at'],
    } for r in rows if (r['reflection'] or '').strip()]

    teams = []
    if scope == 'all':
        codes = client.query(
            """SELECT DISTINCT REGION_CODE FROM MEMBER_AFFILIATION_HISTORIES
                WHERE IS_CURRENT = 1 AND REGION_CODE IS NOT NULL AND REGION_CODE != '0' ORDER BY REGION_CODE"""
        )
        teams = [{'teamId': c['region_code'], 'name': f"{c['region_code']}지역"} for c in codes]

    return JsonResponse({'success': True, 'scope': scope, 'teams': teams,
                         'dateFrom': date_from, 'dateTo': date_to, 'list': items})

