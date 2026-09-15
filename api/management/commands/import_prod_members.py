# 프로덕션 USERS(전체 팀 또는 --team-id 하나) → dev MEMBERS/MEMBER_AFFILIATION_HISTORIES/
# MEMBER_POSITION_MAPPINGS로 직접 임포트. 프로덕션 쪽은 SELECT만 사용 — 절대 쓰기 안 함.
# import_prod_team.py(레거시 USERS 테이블용, 이제 아무 코드도 안 읽음)를 대체하는
# MEMBERS 스키마 버전 — dev MEMBERS에 이미 있는 MEMBER_ID는 건너뜀(재실행 안전).
import json
import re

from django.core.management.base import BaseCommand

from api.clients.data_router import DataRouterClient, DataRouterError

# dev DB엔 TEAMS/AREAS(DISPLAY_NAME) 테이블이 없어서 'team_4'/'area_4_4' 같은
# prod 원본 ID를 화면에 그대로 노출하면 안 예쁨 — 팀 코드/구역 번호만 남긴다.
_TEAM_RE = re.compile(r'team_(\d+)')
_AREA_RE = re.compile(r'area_\d+_(\d+)')


def simplify_team_id(team_id):
    m = _TEAM_RE.fullmatch(team_id or '')
    return m.group(1) if m else team_id


def simplify_area_id(area_id):
    m = _AREA_RE.fullmatch(area_id or '')
    return m.group(1) if m else area_id


class Command(BaseCommand):
    help = '프로덕션 USERS(전체 또는 --team-id)를 dev MEMBERS/MEMBER_AFFILIATION_HISTORIES/MEMBER_POSITION_MAPPINGS로 임포트한다.'

    def add_arguments(self, parser):
        parser.add_argument('--team-id', default=None, help='prod TEAM_ID(예: team_4) — 생략하면 전체 팀')
        parser.add_argument('--prod-url', default='http://localhost:8081')

    def handle(self, *args, **options):
        prod = DataRouterClient(url=options['prod_url'])
        dev = DataRouterClient()  # settings.DATA_ROUTER_URL (dev, :8080)

        sql = """SELECT SABUN, NAME, TEAM_ID, AREA_ID, GMAIL, TELEGRAM_ID, STATUS, ROLE_IDS, GOALS
                   FROM USERS WHERE DELETED_AT IS NULL"""
        args_ = []
        if options['team_id']:
            sql += ' AND TEAM_ID = :1'
            args_ = [options['team_id']]
        rows = prod.query(sql + ' ORDER BY TEAM_ID, NAME', args_)
        self.stdout.write(f'{len(rows)} rows fetched from prod')

        existing = {r['member_id'] for r in dev.query('SELECT MEMBER_ID FROM MEMBERS', [])}

        inserted = skipped = 0
        for r in rows:
            sabun = r['sabun']
            if sabun in existing:
                skipped += 1
                continue

            try:
                role_ids = json.loads(r['role_ids']) if r['role_ids'] else []
            except (TypeError, ValueError):
                role_ids = []

            stmts = [{
                'sql': """INSERT INTO MEMBERS (MEMBER_ID, NAME, STATUS, GMAIL, TELEGRAM_ID, GOALS, CREATED_BY, UPDATED_BY)
                          VALUES (:1, :2, :3, :4, :5, :6, 'SYSTEM', 'SYSTEM')""",
                'args': [sabun, r['name'], (r['status'] or 'active').upper(), r['gmail'], r['telegram_id'], r['goals']],
            }, {
                'sql': """INSERT INTO MEMBER_AFFILIATION_HISTORIES (MEMBER_ID, REGION_CODE, DISTRICT_CODE, START_DATE, IS_CURRENT)
                          VALUES (:1, :2, :3, SYSDATE, 1)""",
                'args': [sabun, simplify_team_id(r['team_id']), simplify_area_id(r['area_id'])],
            }]
            for role_id in role_ids:
                stmts.append({
                    'sql': "INSERT INTO MEMBER_POSITION_MAPPINGS (MEMBER_ID, POSITION_CODE, ASSIGNED_AT) VALUES (:1, :2, SYSDATE)",
                    'args': [sabun, role_id],
                })

            try:
                dev.tx(stmts)
                inserted += 1
            except DataRouterError as e:
                self.stderr.write(self.style.ERROR(f'{sabun} {r["name"]}: {e.code} — {e}'))

        self.stdout.write(self.style.SUCCESS(f'{inserted} inserted, {skipped} already existed, {len(rows)} total from prod'))
