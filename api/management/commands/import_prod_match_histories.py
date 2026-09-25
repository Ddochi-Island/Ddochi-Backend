# 실서버 PROSPECT_MEETINGS(만남 이력) → SARANG_MATCH_HISTORIES 마이그레이션.
# import_prod_sarang으로 옮긴 SARANG 행들 대상 — 그때는 SARANG_MATCH_HISTORIES를
# 범위 밖으로 뺐었는데(OUTCOME 자유텍스트 매핑이 미확정이라), MATCH_RESULT_CODES/
# MATCH_SUB_REASON_CODES(sql/11_match_result_codes.sql)의 LABEL이 레거시 OUTCOME
# 문자열과 대부분 정확히 일치해서 이제 매핑 가능(2026-09-25).
#
# MATCH_DEGREE/ATTEMPT_COUNT: 레거시 PROSPECT_MEETINGS.ROUND_LABEL은 실데이터가
# 전부 'centerFix'라 교사 차수 구분에 못 씀 — 그래서 전부 MATCH_DEGREE=1로 두고,
# 같은 SARANG의 만남을 시간순으로 ATTEMPT_COUNT 1,2,3...으로 증가시킴(스펙의
# "밀릴 때마다 새 행 INSERT, ATTEMPT_COUNT 증가" 관례와 맞음 — 실제 교사가
# 바뀌었는지는 레거시 데이터로 구분 불가라 단순화).
import uuid

from django.core.management.base import BaseCommand

from api.clients.data_router import DataRouterClient
from api.management.commands.import_prod_sarang import _ts, _trunc, _tsx

# 레거시 OUTCOME(자유텍스트) → (RESULT_CODE, SUB_CODE) — MATCH_SUB_REASON_CODES.LABEL과
# 문자열이 정확히 일치하는 것들은 그대로 매핑, 안 맞는 것(매칭취소 세부/거리비합)은
# RESULT만 잡고 SUB_REASON은 비워둠(억지로 끼워맞추지 않음).
_OUTCOME_MAP = {
    '⭕️2차만남': ('SECOND_MEET', None),
    '⭕️상담따기': ('CONSULT_WIN', None),
    '❌밀림': ('DELAY', None),
    '❌경계취소': ('CANCEL', 'BOUNDARY_CANCEL'),
    '❌갈부취소': ('CANCEL', 'CONFLICT_CANCEL'),
    '❌환경취소': ('CANCEL', 'ENV_CANCEL'),
    '❌연두취소': ('CANCEL', 'CONTACT_LOST_CANCEL'),
    '⭕️환경비합': ('UNFIT', 'ENV_UNFIT'),
    '⭕️인성비합': ('UNFIT', 'PERSONALITY_UNFIT'),
    '⭕️정신질환': ('UNFIT', 'MENTAL_HEALTH'),
    '⭕️건강비합': ('UNFIT', 'HEALTH_UNFIT'),
    '⭕️경계탈락': ('DROPOUT', 'BOUNDARY_DROPOUT'),
    '⭕️갈부탈락': ('DROPOUT', 'CONFLICT_DROPOUT'),
    # 아래는 MATCH_SUB_REASON_CODES에 정확히 대응하는 코드가 없어 RESULT만 매핑:
    '❌매칭취소(의심/경계)': ('CANCEL', 'BOUNDARY_CANCEL'),  # "의심/경계"라 경계취소로 근사
    '❌매칭취소(답장안옴)': ('CANCEL', 'CONTACT_LOST_CANCEL'),  # "답장안옴" = 연두(연락두절)
    '❌매칭취소(메리트부족)': ('CANCEL', None),
    '❌매칭취소(대면부담)': ('CANCEL', None),
    '⭕️거리비합': ('UNFIT', None),  # ENV_UNFIT과 결이 다를 수 있어 서브사유는 비워둠
}


class Command(BaseCommand):
    help = '이미 마이그레이션된 SARANG 행들에 실서버 PROSPECT_MEETINGS 이력을 SARANG_MATCH_HISTORIES로 채운다.'

    def add_arguments(self, parser):
        parser.add_argument('--prod-url', default='http://localhost:8081')

    def handle(self, *args, **options):
        prod = DataRouterClient(url=options['prod_url'], timeout_ms=30000)
        dev = DataRouterClient()
        FETCH_LIMIT = 5000

        prospects = prod.query(
            "SELECT PROSPECT_ID, PERSONAL_INFO_ID, CREATED_AT FROM PROSPECTS WHERE IS_DROPPED = '0'",
            fetch_limit=FETCH_LIMIT,
        )
        meetings = prod.query(
            "SELECT PROSPECT_ID, SCHEDULED_AT, PLACE, OUTCOME FROM PROSPECT_MEETINGS ORDER BY SCHEDULED_AT",
            fetch_limit=FETCH_LIMIT,
        )
        meetings_by_prospect = {}
        for m in meetings:
            meetings_by_prospect.setdefault(m['prospect_id'], []).append(m)

        dev_sarang = dev.query(
            'SELECT SARANG_ID, PERSONAL_INFO_ID, CREATED_AT FROM SARANG', fetch_limit=FETCH_LIMIT
        )
        sarang_by_key = {(r['personal_info_id'], _ts(r['created_at'])): r['sarang_id'] for r in dev_sarang}

        existing = {
            r['sarang_id']
            for r in dev.query('SELECT DISTINCT SARANG_ID FROM SARANG_MATCH_HISTORIES', fetch_limit=FETCH_LIMIT)
        }

        matched_prospects = 0
        inserted = 0
        skipped_no_outcome_map = 0

        for p in prospects:
            key = (p['personal_info_id'], _ts(p['created_at']))
            sarang_id = sarang_by_key.get(key)
            if not sarang_id or sarang_id in existing:
                continue
            rounds = meetings_by_prospect.get(p['prospect_id']) or []
            if not rounds:
                continue

            matched_prospects += 1
            for attempt, m in enumerate(rounds, start=1):
                outcome = m['outcome']
                result_code, sub_code = _OUTCOME_MAP.get(outcome, (None, None))
                if outcome and not result_code:
                    skipped_no_outcome_map += 1
                status = 'FINISHED' if result_code else 'SCHEDULED'
                match_id = uuid.uuid4().hex.upper()
                dev.exec(
                    'INSERT INTO SARANG_MATCH_HISTORIES '
                    '(MATCH_ID, SARANG_ID, MATCH_DEGREE, ATTEMPT_COUNT, MATCHED_AT, MATCH_LOCATION, STATUS, RESULT, SUB_REASON, CREATED_AT) '
                    f'VALUES (:1, :2, :3, :4, {_tsx(5)}, :6, :7, :8, :9, {_tsx(10)})',
                    [
                        match_id, sarang_id, 1, attempt, _ts(m['scheduled_at']), _trunc(m['place'], 100),
                        status, result_code, sub_code, _ts(m['scheduled_at']),
                    ],
                )
                inserted += 1
            existing.add(sarang_id)

        self.stdout.write(self.style.SUCCESS(
            f'{matched_prospects} prospects matched, {inserted} match-history rows inserted, '
            f'{skipped_no_outcome_map} OUTCOME strings unmapped (RESULT left NULL)'
        ))
