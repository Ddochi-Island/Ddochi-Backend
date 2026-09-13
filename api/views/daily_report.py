"""dailyReport.js 포팅 대상 — daily_report 라우트 스텁 (구조만, 로직은 미구현).
daily_report/daily_report_get/daily_report_list_names 셋만 실제 구현 — 나머지(주간
계획/plan-execution/reflections 등)는 별개의 "일일 계획" 서브시스템이라 범위 밖."""
import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from api.auth.gate import get_author_context, require_jwt
from api.clients.data_router import DataRouterClient
from api.util.business_date import get_business_date
from api.views.assets import _member_id_by_name

logger = logging.getLogger('api.views.daily_report')


def _json_body(request):
    try:
        return json.loads(request.body or b'{}')
    except (TypeError, ValueError):
        return {}


@csrf_exempt
@require_jwt
def daily_report_list_names(request, *args, **kwargs):
    """보고 대상자 autocomplete 명단 — 작성자와 같은 지역 소속 전원 + 이미 그
    dateKey에 보고서를 낸 다른 지역 사람(팀장 대리 제출 등 케이스 커버)."""
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
                  PROMO_LIST, REG_LIST, IS_FINAL, SUBMITTED_AT
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
            'activity': row['activity'],
            'talkCount': int(row['talk_count'] or 0),
            'dmCount': int(row['dm_count'] or 0),
            'qrCount': int(row['qr_count'] or 0),
            'onlineIntakeCount': int(row['online_intake_count'] or 0),
            'promoList': row['promo_list'] or '',
            'regList': reg_list,
            'isFinal': row['is_final'] == '1',
            'submittedAt': row['submitted_at'],
        },
    })


@csrf_exempt
@require_jwt
def daily_report(request, *args, **kwargs):
    """일일보고 제출(upsert) — 제출 성공 후 그 사람 소속 지역의 일일보고 텔레그램
    메시지를 갱신(기존 메시지 있을 때만 edit, 없으면 조용히 skip — 새로 만드는 건
    정각 크론 몫)."""
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    body = _json_body(request)
    name = str(body.get('name') or '').strip()
    date_key = str(body.get('dateKey') or body.get('confirmedDateKey') or '').strip() or get_business_date()
    activity = str(body.get('activity') or 'none').strip()
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

    client.exec(
        """MERGE INTO DAILY_REPORTS dr
           USING (SELECT TO_DATE(:1, 'YYYY-MM-DD') AS REPORT_DATE, :2 AS MEMBER_ID FROM dual) src
              ON (dr.REPORT_DATE = src.REPORT_DATE AND dr.MEMBER_ID = src.MEMBER_ID)
         WHEN MATCHED THEN UPDATE SET
                AUTHOR_MEMBER_ID = :3, ACTIVITY = :4, TALK_COUNT = :5, DM_COUNT = :6,
                QR_COUNT = :7, ONLINE_INTAKE_COUNT = :8, PROMO_LIST = :9, REG_LIST = :10,
                IS_FINAL = :11, SNAP_REGION_CODE = :12, SNAP_DISTRICT_CODE = :13,
                SUBMITTED_AT = SYSTIMESTAMP, UPDATED_AT = SYSTIMESTAMP, UPDATED_BY = :14
         WHEN NOT MATCHED THEN INSERT
                (REPORT_DATE, MEMBER_ID, AUTHOR_MEMBER_ID, ACTIVITY, TALK_COUNT, DM_COUNT,
                 QR_COUNT, ONLINE_INTAKE_COUNT, PROMO_LIST, REG_LIST, IS_FINAL,
                 SNAP_REGION_CODE, SNAP_DISTRICT_CODE, CREATED_BY, UPDATED_BY)
              VALUES (TO_DATE(:15, 'YYYY-MM-DD'), :16, :17, :18, :19, :20,
                      :21, :22, :23, :24, :25, :26, :27, :28, :29)""",
        [
            date_key, member_id,
            author_sabun, activity, _int(body.get('talkCount')), _int(body.get('dmCount')),
            _int(body.get('qrCount')), _int(body.get('onlineIntakeCount')), str(body.get('promoList') or ''), reg_list_json,
            1 if body.get('isFinal') else 0, target_ctx['team_id'], target_ctx['area_id'],
            author_sabun,
            date_key, member_id, author_sabun, activity, _int(body.get('talkCount')), _int(body.get('dmCount')),
            _int(body.get('qrCount')), _int(body.get('onlineIntakeCount')), str(body.get('promoList') or ''), reg_list_json,
            1 if body.get('isFinal') else 0, target_ctx['team_id'], target_ctx['area_id'], author_sabun, author_sabun,
        ],
    )

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


@csrf_exempt
def daily_report_reflections(request, *args, **kwargs):
    # TODO: services/main/src/routes/dailyReport.js 의 POST /daily-report/reflections 포팅
    if request.method not in ['POST']:
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    return JsonResponse({"error": "not_implemented", "source": "services/main/src/routes/dailyReport.js"}, status=501)

