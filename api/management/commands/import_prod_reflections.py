# 실서버(레거시) DAILY_REPORTS의 느낀점(REFLECTION)/기분(MOOD)을 v2 DAILY_REPORTS로 복구하는 일회성 커맨드
# 프로덕션 쪽은 SELECT만 사용. 레거시 SABUN = v2 MEMBER_ID(import_prod_members가 그대로 옮김).
# - 같은 (날짜, 사람)의 v2 보고가 있으면: 느낀점이 비어 있을 때만 MOOD/REFLECTION 채움(v2 입력 우선)
# - 없으면: 느낀점 열람에 필요한 최소 보고 행을 새로 만듦(활동/DM/QR은 레거시 값, 홍보목록은 형식이
#   달라서 안 옮김). 재실행해도 안전(이미 채워진 건 건너뜀). --dry-run으로 먼저 건수 확인 권장.
from datetime import datetime, timezone

from django.core.management.base import BaseCommand

from api.clients.data_router import DataRouterClient, DataRouterError
from api.management.commands.import_prod_members import simplify_area_id, simplify_team_id

_ACTIVITIES = {'none', 'online', 'offline', 'offlineSearch'}
_TS_MASK = 'YYYY-MM-DD"T"HH24:MI:SS.FF6"Z"'


def _utc(iso_str):
    # data_router 타임스탬프 문자열을 실제 UTC로 변환(오프셋이 붙어 와도 9시간 밀리지 않게)
    if not iso_str:
        return None
    dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f') + 'Z'


def _mood(v):
    try:
        m = int(v)
    except (TypeError, ValueError):
        return None
    return m if 1 <= m <= 10 else None


class Command(BaseCommand):
    help = '레거시 DAILY_REPORTS의 느낀점/기분을 v2 DAILY_REPORTS로 복구한다.'

    def add_arguments(self, parser):
        parser.add_argument('--prod-url', default='http://localhost:8081')
        parser.add_argument('--dry-run', action='store_true', help='쓰지 않고 건수만 출력')

    def handle(self, *args, **options):
        prod = DataRouterClient(url=options['prod_url'], timeout_ms=60000)
        dev = DataRouterClient(timeout_ms=30000)
        dry = options['dry_run']

        rows = prod.query(
            """SELECT TO_CHAR(REPORT_DATE, 'YYYY-MM-DD') AS RD, SABUN, AUTHOR_SABUN, ACTIVITY,
                      DM_COUNT, QR_COUNT, MOOD, REFLECTION, SUBMITTED_AT, SNAP_TEAM_ID, SNAP_AREA_ID
                 FROM DAILY_REPORTS
                WHERE DELETED_AT IS NULL AND REFLECTION IS NOT NULL AND DBMS_LOB.GETLENGTH(REFLECTION) > 0
                ORDER BY REPORT_DATE""",
            fetch_limit=50000,
        )
        rows = [r for r in rows if (r['reflection'] or '').strip()]
        self.stdout.write(f'레거시 느낀점 {len(rows)}건 ({rows[0]["rd"] if rows else "-"} ~ {rows[-1]["rd"] if rows else "-"})')

        members = {r['member_id'] for r in dev.query('SELECT MEMBER_ID FROM MEMBERS', fetch_limit=50000)}
        existing = {
            (r['rd'], r['member_id']): r['has_ref'] == '1'
            for r in dev.query(
                """SELECT TO_CHAR(REPORT_DATE, 'YYYY-MM-DD') AS RD, MEMBER_ID,
                          CASE WHEN REFLECTION IS NULL THEN 0 ELSE 1 END AS HAS_REF FROM DAILY_REPORTS""",
                fetch_limit=50000,
            )
        }

        updates, inserts, skipped_member, skipped_filled = [], [], 0, 0
        for r in rows:
            sabun = r['sabun']
            if sabun not in members:
                skipped_member += 1
                continue
            key = (r['rd'], sabun)
            mood = _mood(r['mood'])
            if key in existing:
                if existing[key]:
                    skipped_filled += 1
                    continue
                updates.append({
                    'sql': """UPDATE DAILY_REPORTS SET MOOD = :1, REFLECTION = :2
                               WHERE REPORT_DATE = TO_DATE(:3, 'YYYY-MM-DD') AND MEMBER_ID = :4 AND REFLECTION IS NULL""",
                    'args': [mood, r['reflection'], r['rd'], sabun],
                })
            else:
                author = r['author_sabun'] if r['author_sabun'] in members else sabun
                activity = r['activity'] if r['activity'] in _ACTIVITIES else 'none'
                submitted = _utc(r['submitted_at'])
                inserts.append({
                    'sql': f"""INSERT INTO DAILY_REPORTS
                                 (REPORT_DATE, MEMBER_ID, AUTHOR_MEMBER_ID, ACTIVITY, DM_COUNT, QR_COUNT, IS_FINAL,
                                  SNAP_REGION_CODE, SNAP_DISTRICT_CODE, MOOD, REFLECTION, SUBMITTED_AT, CREATED_BY, UPDATED_BY)
                               VALUES (TO_DATE(:1, 'YYYY-MM-DD'), :2, :3, :4, :5, :6, 1, :7, :8, :9, :10,
                                       NVL(TO_TIMESTAMP_TZ(:11, '{_TS_MASK}'), SYSTIMESTAMP), 'import_prod', 'import_prod')""",
                    'args': [r['rd'], sabun, author, activity, int(r['dm_count'] or 0), int(r['qr_count'] or 0),
                             simplify_team_id(r['snap_team_id']), simplify_area_id(r['snap_area_id']),
                             mood, r['reflection'], submitted],
                })

        self.stdout.write(
            f'v2 기존 보고에 채움 {len(updates)}건 / 새 보고 행 {len(inserts)}건 / '
            f'이미 v2 느낀점 있어 건너뜀 {skipped_filled}건 / v2에 없는 회원이라 건너뜀 {skipped_member}건'
        )
        if dry:
            self.stdout.write(self.style.WARNING('--dry-run: 아무것도 쓰지 않음'))
            return

        done = failed = 0
        stmts = updates + inserts
        for i in range(0, len(stmts), 50):
            chunk = stmts[i:i + 50]
            try:
                dev.tx(chunk)
                done += len(chunk)
            except DataRouterError:
                for st in chunk:  # 한 건 때문에 묶음 전체가 실패하지 않게 개별 재시도
                    try:
                        dev.exec(st['sql'], st['args'])
                        done += 1
                    except DataRouterError as e:
                        failed += 1
                        self.stderr.write(f"실패 {st['args'][:4]}: {e}")
        self.stdout.write(self.style.SUCCESS(f'완료 {done}건, 실패 {failed}건'))
