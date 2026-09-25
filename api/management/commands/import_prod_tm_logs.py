# 실서버 PROSPECT_TM_LOGS → TM_LOGS/SARANG_ACTIVITY_LOGS 마이그레이션.
# 레거시 CATEGORY 7종을 실측(2026-09-25, 5000행 제한 안 걸고 전수 조회)한 결과:
#   meetingFix/tmReserved/noAnswer/bihap/rejected → 통화 결과(TM_LOGS)
#   welcomeMsg/noAnswerMsg                        → 문자 발송 이벤트(SARANG_ACTIVITY_LOGS)
# 이게 정확히 sql/07_sarang.sql이 "TM_PHASE/CATEGORY 병합 문제"라고 부른
# 것 — 레거시는 통화 결과와 문자 발송 이벤트를 한 테이블/enum에 다 넣었는데
# v2는 의도적으로 분리했음. 스키마 doc의 CATEGORY 6종('longTerm' 포함)은
# 실데이터와 다름(longTerm 실사용 0건, welcomeMsg/noAnswerMsg는 doc에 없음) —
# 항상 실측 우선.
import uuid

from django.core.management.base import BaseCommand

from api.clients.data_router import DataRouterClient
from api.management.commands.import_prod_sarang import _ts, _tsx

# CATEGORY → TM_RESULT_CODES.RESULT_CODE (통화 결과만)
_TM_RESULT_MAP = {
    'meetingFix': 'MEET_FIX',
    'tmReserved': 'RESERVED_TM',
    'noAnswer': 'NO_ANSWER',
    'bihap': 'UNFIT',
    'rejected': 'REJECT',
}
# CATEGORY → SARANG_ACTIVITY_LOGS.EVENT_TYPE (문자 발송 이벤트만)
_ACTIVITY_EVENT_MAP = {
    'welcomeMsg': '선문자발송',
    'noAnswerMsg': '부재중문자발송',
}


class Command(BaseCommand):
    help = '이미 마이그레이션된 SARANG 행들에 실서버 PROSPECT_TM_LOGS를 TM_LOGS/SARANG_ACTIVITY_LOGS로 채운다.'

    def add_arguments(self, parser):
        parser.add_argument('--prod-url', default='http://localhost:8081')

    def handle(self, *args, **options):
        prod = DataRouterClient(url=options['prod_url'], timeout_ms=30000)
        dev = DataRouterClient()
        FETCH_LIMIT = 10000

        prospects = prod.query(
            "SELECT PROSPECT_ID, PERSONAL_INFO_ID, CREATED_AT FROM PROSPECTS WHERE IS_DROPPED = '0'",
            fetch_limit=FETCH_LIMIT,
        )
        dev_sarang = dev.query('SELECT SARANG_ID, PERSONAL_INFO_ID, CREATED_AT FROM SARANG', fetch_limit=FETCH_LIMIT)
        sarang_by_key = {(r['personal_info_id'], _ts(r['created_at'])): r['sarang_id'] for r in dev_sarang}
        sarang_id_by_prospect = {}
        for p in prospects:
            key = (p['personal_info_id'], _ts(p['created_at']))
            sid = sarang_by_key.get(key)
            if sid:
                sarang_id_by_prospect[p['prospect_id']] = sid

        tm_logs = prod.query(
            'SELECT PROSPECT_ID, CATEGORY, CONTENT, AUTHOR_SABUN, EVENT_AT FROM PROSPECT_TM_LOGS ORDER BY EVENT_AT',
            fetch_limit=FETCH_LIMIT,
        )

        existing_tm = {
            r['sarang_id'] for r in dev.query('SELECT DISTINCT SARANG_ID FROM TM_LOGS', fetch_limit=FETCH_LIMIT)
        }
        existing_activity = {
            r['sarang_id']
            for r in dev.query('SELECT DISTINCT SARANG_ID FROM SARANG_ACTIVITY_LOGS', fetch_limit=FETCH_LIMIT)
        }

        tm_inserted = 0
        activity_inserted = 0
        skipped_no_sarang = 0
        skipped_unmapped_category = 0
        touched_sarang_tm = set()
        touched_sarang_activity = set()

        for t in tm_logs:
            sarang_id = sarang_id_by_prospect.get(t['prospect_id'])
            if not sarang_id:
                skipped_no_sarang += 1
                continue

            category = t['category']
            if category in _TM_RESULT_MAP:
                if sarang_id in existing_tm:
                    continue
                result_code = _TM_RESULT_MAP[category]
                dev.exec(
                    'INSERT INTO TM_LOGS (TM_ID, SARANG_ID, CALLER_MEMBER_ID, RESULT, MEMO, CREATED_AT) '
                    f'VALUES (:1, :2, :3, :4, :5, {_tsx(6)})',
                    [uuid.uuid4().hex.upper(), sarang_id, t['author_sabun'], result_code, t['content'], _ts(t['event_at'])],
                )
                tm_inserted += 1
                touched_sarang_tm.add(sarang_id)
            elif category in _ACTIVITY_EVENT_MAP:
                if sarang_id in existing_activity:
                    continue
                event_type = _ACTIVITY_EVENT_MAP[category]
                dev.exec(
                    'INSERT INTO SARANG_ACTIVITY_LOGS (ACTIVITY_ID, SARANG_ID, ACTOR_MEMBER_ID, EVENT_TYPE, CONTENT, CREATED_AT) '
                    f'VALUES (:1, :2, :3, :4, :5, {_tsx(6)})',
                    [uuid.uuid4().hex.upper(), sarang_id, t['author_sabun'], event_type, t['content'], _ts(t['event_at'])],
                )
                activity_inserted += 1
                touched_sarang_activity.add(sarang_id)
            else:
                skipped_unmapped_category += 1

        self.stdout.write(self.style.SUCCESS(
            f'TM_LOGS {tm_inserted}건 ({len(touched_sarang_tm)} sarang), '
            f'SARANG_ACTIVITY_LOGS {activity_inserted}건 ({len(touched_sarang_activity)} sarang), '
            f'skipped {skipped_no_sarang} (no matching SARANG), {skipped_unmapped_category} (unmapped category)'
        ))
