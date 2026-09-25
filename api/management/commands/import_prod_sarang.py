# 실서버 PROSPECTS(활성, IS_DROPPED=0) → SARANG 계열 테이블 마이그레이션.
# 스코프: 현재 상태(신원/현재 합재양 스냅샷)만 옮김 — TM_LOGS/SARANG_ACTIVITY_LOGS/
# SARANG_MATCH_HISTORIES(통화·매칭 회차 이력)는 별도 작업으로 미룸(카테고리→RESULT
# enum 매핑이 별도 검토 필요해서 범위 밖으로 뺌 — 2026-09-25 결정).
#
# STAGE 판정 로직(실데이터 분포 확인 후 확정):
#   STATUS='phoneSearch' → TM_STATUS in (None,'before')면 '유입', 아니면 '티엠'
#   STATUS='meetingFix'  → 활성 합재양 없으면 '만픽'
#                          있고 APPROVAL_STATUS in (None,'rejected')면 '합재양'
#                          APPROVAL_STATUS='approved'면: 최신 PROSPECT_MEETINGS.OUTCOME이
#                          '⭕️상담따기'면 '상따', 그 외(2차만남/밀림/NULL)는 '매칭'
#
# PERSONAL_INFO_ID는 레거시 HASH_ID를 그대로 재사용(둘 다 SHA-256(name+phone) —
# 동일인 재신청 시 자동 연결되는 동작 유지). 프로덕션 쪽은 SELECT만 사용.
import uuid
from datetime import datetime

from django.core.management.base import BaseCommand

from api.clients.data_router import DataRouterClient, DataRouterError

_OUTCOME_SANGDAN = '⭕️상담따기'
_TS_MASK = 'YYYY-MM-DD"T"HH24:MI:SS.FF6"Z"'


def _ts(iso_str):
    # data_router가 돌려주는 타임스탬프 문자열은 초 단위 정밀도가 0이면
    # 소수점 이하를 통째로 생략함('...13:00:00Z' vs '...04:26:57.050827Z') —
    # 고정폭 TO_TIMESTAMP_TZ 마스크로 바로 바인딩하면 그 경우만 ORA-01843 남.
    # 여기서 항상 마이크로초 6자리로 맞춰서 반환.
    if not iso_str:
        return None
    dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
    return dt.strftime('%Y-%m-%dT%H:%M:%S.%f') + 'Z'


def _tsx(n):
    return f'TO_TIMESTAMP_TZ(:{n}, \'{_TS_MASK}\')'


def _trunc(s, max_bytes):
    # 레거시 자유텍스트 컬럼(CLOB/VARCHAR2(1000) 등)이 v2의 더 좁은 VARCHAR2로
    # 들어갈 때 길이 초과(ORA-12899) 방지. SARANG_HAB_JAE_YANG의 실제 배포된
    # 컬럼들은 SQL 소스엔 "VARCHAR2(255 CHAR)"로 돼있지만 실측(USER_TAB_COLUMNS.
    # CHAR_USED='B')해보니 실제로는 바이트 세맨틱스로 배포돼있음(소스 파일과
    # 실DB가 어긋남, char_used='B') — 문자수 기준으로 잘라도 한글은 3바이트라
    # ORA-12899가 다시 남. 그래서 항상 바이트 길이 기준으로 자름.
    if not s:
        return s
    b = s.encode('utf-8')
    if len(b) <= max_bytes:
        return s
    return b[:max_bytes].decode('utf-8', errors='ignore')


def _derive_stage(status, tm_status, has_active_hjy, approval_status, latest_outcome):
    if status == 'phoneSearch':
        return '유입' if tm_status in (None, 'before') else '티엠'
    # meetingFix
    if not has_active_hjy:
        return '만픽'
    if approval_status in (None, 'rejected'):
        return '합재양'
    return '상따' if latest_outcome == _OUTCOME_SANGDAN else '매칭'


class Command(BaseCommand):
    help = '프로덕션 활성(IS_DROPPED=0) PROSPECTS를 SARANG 계열 테이블로 마이그레이션한다.'

    def add_arguments(self, parser):
        parser.add_argument('--prod-url', default='http://localhost:8081')

    def handle(self, *args, **options):
        # 기본 15s 클라이언트 소켓 타임아웃 — 조회당(.query()) timeout_ms 인자는
        # 서버에만 전달될 뿐 실제 소켓 read timeout엔 영향 없음(DataRouterClient._post가
        # 생성 시점의 self.timeout_ms만 씀) — 그래서 생성자에서 넉넉하게 잡아야 함.
        # 큰 조회(1.8MB대, PROSPECT_HABJAEYANG)가 기본값을 가끔 넘겨서 타임아웃 났었음.
        prod = DataRouterClient(url=options['prod_url'], timeout_ms=30000)
        dev = DataRouterClient()

        # data_router 기본 fetch_limit=1000 — 이 테이블들 전부 1000행을 넘을 수 있어서
        # 명시적으로 넉넉히 잡아야 함(안 잡으면 조인 대상이 조용히 잘려서 STAGE 오판정됨,
        # 드라이런 중 실제로 겪은 버그).
        FETCH_LIMIT = 5000

        prospects = prod.query(
            "SELECT p.PROSPECT_ID, p.PERSONAL_INFO_ID, p.MANAGER_SABUN, p.GUIDE_SABUN, "
            "p.TEACHER_SABUN, p.TEACHER_NAME, p.STATUS, p.APPROVAL_STATUS, p.TM_STATUS, "
            "p.AGE, p.GENDER, p.ON_OFF, p.TOOL, p.PATH, p.DROPPED_REASON, "
            "p.CREATED_AT, p.UPDATED_AT, p.CREATED_BY, p.UPDATED_BY "
            "FROM PROSPECTS p WHERE p.IS_DROPPED = '0'",
            fetch_limit=FETCH_LIMIT,
        )
        self.stdout.write(f'{len(prospects)} active prospects fetched from prod')

        pi_rows = prod.query(
            'SELECT HASH_ID, NAME, PHONE, PHONE_NORMALIZED, RESIDENCE, CREATED_AT FROM PERSONAL_INFO',
            fetch_limit=FETCH_LIMIT,
        )
        personal_info = {r['hash_id']: r for r in pi_rows}

        hjy_rows = prod.query(
            "SELECT h.PROSPECT_ID, h.MBTI, h.JOB, h.ATT, h.DIST, h.ETC, h.CENTER_ENV, h.DRUG, h.MENTAL, "
            "h.SELF_IMAGE, h.GWACHEON_MIN, h.GWACHEON_TRANSFER, h.CENTER_MIN, h.CENTER_TRANSFER, "
            "h.PURPOSE, h.QNA, h.PLAN_TEXT, h.SCHEDULE_TEXT, h.TROUBLE, h.WARY, h.TM_USER_SABUN, "
            "h.REPLIED, h.WINDOW_OPENED, h.CREATED_AT "
            "FROM PROSPECT_HABJAEYANG h WHERE h.ACTIVE = '1'",
            fetch_limit=FETCH_LIMIT,
        )
        habjaeyang = {r['prospect_id']: r for r in hjy_rows}

        meeting_rows = prod.query(
            "SELECT PROSPECT_ID, OUTCOME, SCHEDULED_AT, PLACE FROM ("
            "  SELECT m.*, ROW_NUMBER() OVER (PARTITION BY m.PROSPECT_ID ORDER BY m.SCHEDULED_AT DESC, m.MEETING_ID DESC) AS rn"
            "  FROM PROSPECT_MEETINGS m"
            ") WHERE rn = 1",
            fetch_limit=FETCH_LIMIT,
        )
        latest_meeting = {r['prospect_id']: r for r in meeting_rows}

        existing_pi = {
            r['personal_info_id']
            for r in dev.query('SELECT PERSONAL_INFO_ID FROM SARANG_PERSONAL_INFO', fetch_limit=FETCH_LIMIT)
        }
        # 재실행 대비 idempotency: 이전 실행이 도중에 실패해도 이미 만든 SARANG은
        # 재사용하고, 아직 없는 INFLOW_DETAILS/HAB_JAE_YANG만 이어서 채워 넣음
        # (테이블별로 독립 체크 — 한 프로스펙트 처리 중 일부만 성공했을 수 있어서
        # "SARANG 있으면 그 행 전체를 스킵"하면 나머지 자식 테이블이 영영 안 채워짐).
        existing_sarang = {
            (r['personal_info_id'], r['created_at']): r['sarang_id']
            for r in dev.query('SELECT SARANG_ID, PERSONAL_INFO_ID, CREATED_AT FROM SARANG', fetch_limit=FETCH_LIMIT)
        }
        existing_inflow = {
            r['sarang_id'] for r in dev.query('SELECT SARANG_ID FROM SARANG_INFLOW_DETAILS', fetch_limit=FETCH_LIMIT)
        }
        existing_hjy = {
            r['sarang_id']
            for r in dev.query("SELECT SARANG_ID FROM SARANG_HAB_JAE_YANG WHERE IS_ACTIVE = '1'", fetch_limit=FETCH_LIMIT)
        }

        skipped_no_owner = 0
        skipped_dup = 0
        migrated = 0
        migrated_hjy = 0

        for p in prospects:
            pid = p['prospect_id']
            personal_info_id = p['personal_info_id']
            pi = personal_info.get(personal_info_id)
            if pi is None:
                self.stderr.write(self.style.WARNING(f'{pid}: no PERSONAL_INFO row for {personal_info_id}, skip'))
                continue

            # 'SYSTEM'은 레거시의 시스템 플레이스홀더 사번(실제 담당자 없음) — NULL과
            # 동급으로 취급. 실행 결과 REGION_CODE='0'으로 잡혀서 프론트 팀별 탭
            # 어디에도 안 걸리는 게 실제로 발견돼서(2026-09-25) 추가한 가드.
            manager = p['manager_sabun'] if p['manager_sabun'] != 'SYSTEM' else None
            guide = p['guide_sabun'] if p['guide_sabun'] != 'SYSTEM' else None
            inflow_member_id = manager or guide
            if not inflow_member_id:
                skipped_no_owner += 1
                continue

            hjy = habjaeyang.get(pid)
            meeting = latest_meeting.get(pid)
            stage = _derive_stage(
                p['status'], p['tm_status'], hjy is not None, p['approval_status'],
                meeting['outcome'] if meeting else None,
            )

            sarang_key = (personal_info_id, p['created_at'])
            sarang_id = existing_sarang.get(sarang_key)
            already_had_sarang = sarang_id is not None

            if already_had_sarang:
                skipped_dup += 1
            else:
                if personal_info_id not in existing_pi:
                    dev.exec(
                        'INSERT INTO SARANG_PERSONAL_INFO (PERSONAL_INFO_ID, NAME, PHONE, PHONE_NORMALIZED, RESIDENCE_STATION, CREATED_AT) '
                        f'VALUES (:1, :2, :3, :4, :5, {_tsx(6)})',
                        [
                            personal_info_id, _trunc(pi['name'], 50), _trunc(pi['phone'], 20),
                            _trunc(pi['phone_normalized'], 20), _trunc(pi['residence'], 100), _ts(pi['created_at']),
                        ],
                    )
                    existing_pi.add(personal_info_id)

                sarang_id = uuid.uuid4().hex.upper()
                recruitment_type = 'ONLINE' if p['on_off'] == 'online' else 'OFFLINE'
                dev.exec(
                    'INSERT INTO SARANG (SARANG_ID, PERSONAL_INFO_ID, INFLOW_MEMBER_ID, AGE, GENDER, MBTI, STAGE, '
                    'RECRUITMENT_TYPE, INFLOW_DATE, CREATED_AT, UPDATED_AT, CREATED_BY, UPDATED_BY) '
                    f'VALUES (:1, :2, :3, :4, :5, :6, :7, :8, {_tsx(9)}, {_tsx(10)}, {_tsx(11)}, :12, :13)',
                    [
                        sarang_id, personal_info_id, inflow_member_id, p['age'], p['gender'],
                        hjy['mbti'] if hjy else None, stage, recruitment_type, _ts(p['created_at']),
                        _ts(p['created_at']), _ts(p['updated_at']), p['created_by'], p['updated_by'],
                    ],
                )
                existing_sarang[sarang_key] = sarang_id
                migrated += 1

            if guide and sarang_id not in existing_inflow:
                dev.exec(
                    'INSERT INTO SARANG_INFLOW_DETAILS (SARANG_ID, INTRODUCER_MEMBER_ID) VALUES (:1, :2)',
                    [sarang_id, guide],
                )
                existing_inflow.add(sarang_id)

            if hjy and sarang_id not in existing_hjy:
                etc_parts = [x for x in [hjy['etc']] if x]
                if hjy['trouble']:
                    etc_parts.append(f"[고민] {hjy['trouble']}")
                if hjy['plan_text']:
                    etc_parts.append(f"[향후계획] {hjy['plan_text']}")
                etc = _trunc('\n'.join(etc_parts) or None, 255)

                approval_status = {'approved': 'approved', 'rejected': 'rejected'}.get(p['approval_status'], 'pending')
                reject_reason = p['dropped_reason'] if approval_status == 'rejected' else None
                teacher_name_override = p['teacher_name'] if not p['teacher_sabun'] else None

                hjy_id = uuid.uuid4().hex.upper()
                dev.exec(
                    'INSERT INTO SARANG_HAB_JAE_YANG ('
                    'HAB_JAE_YANG_ID, SARANG_ID, IS_ACTIVE, GUIDE_MEMBER_ID, CALLER_MEMBER_ID, TEACHER_MEMBER_ID, '
                    'ROUTE, TOOL, MATCH_SCHEDULED_AT, MATCH_LOCATION, GWACHEON_TRAVEL_TIME, GWACHEON_TRANSFER_COUNT, '
                    'CENTER_TRAVEL_TIME, CENTER_TRANSFER_COUNT, SCHOOL_MAJOR_JOB, SCHEDULE, APPLICATION_PURPOSE, '
                    'SELF_IMAGE, CHARACTER_NOTE, ALERT_NOTE, DISTANCE_BURDEN, QNA, ETC, HAS_CENTER_ENV, '
                    'IS_TAKING_MEDS, HAS_MENTAL_ILLNESS, HAS_REPLIED, IS_WINDOW_OPENED, IS_JAE_GA, '
                    'APPROVAL_STATUS, REJECT_REASON, TEACHER_NAME_OVERRIDE, CREATED_AT'
                    f') VALUES (:1,:2,:3,:4,:5,:6,:7,:8,{_tsx(9)},:10,:11,:12,:13,:14,:15,:16,:17,:18,:19,:20,:21,:22,:23,:24,:25,:26,:27,:28,:29,:30,:31,:32,{_tsx(33)})',
                    [
                        hjy_id, sarang_id, 1, guide, hjy['tm_user_sabun'], p['teacher_sabun'],
                        _trunc(p['path'], 50), _trunc(p['tool'], 50), _ts(meeting['scheduled_at']) if meeting else None,
                        _trunc(meeting['place'], 100) if meeting else None,
                        hjy['gwacheon_min'], hjy['gwacheon_transfer'], hjy['center_min'], hjy['center_transfer'],
                        _trunc(hjy['job'], 100), _trunc(hjy['schedule_text'], 100), _trunc(hjy['purpose'], 255),
                        _trunc(hjy['self_image'], 255), _trunc(hjy['att'], 255), _trunc(hjy['wary'], 255),
                        _trunc(hjy['dist'], 255), _trunc(hjy['qna'], 1000), etc,
                        1 if hjy['center_env'] == 'O' else 0, 1 if hjy['drug'] == 'O' else 0, 1 if hjy['mental'] == 'O' else 0,
                        hjy['replied'], hjy['window_opened'], 1 if p['approval_status'] == 'approved' else 0,
                        approval_status, _trunc(reject_reason, 500), _trunc(teacher_name_override, 100), _ts(hjy['created_at']),
                    ],
                )
                existing_hjy.add(sarang_id)
                migrated_hjy += 1

        self.stdout.write(self.style.SUCCESS(
            f'migrated {migrated} SARANG rows ({migrated_hjy} with HAB_JAE_YANG), '
            f'skipped {skipped_no_owner} (no manager/guide), {skipped_dup} (already migrated)'
        ))
