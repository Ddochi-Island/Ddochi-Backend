# 프로덕션 USERS 명단 중 특정 TEAM_ID만 dev DB로 복사 (테스트용 시드).
# 프로덕션 쪽은 SELECT만 사용 — 절대 쓰기 안 함.
import re

from django.core.management.base import BaseCommand

from api.clients.data_router import DataRouterClient, DataRouterError

# dev DB엔 TEAMS/AREAS(DISPLAY_NAME) 테이블이 없어서 'team_4'/'area_4_4' 같은
# prod 원본 ID를 화면에 그대로 노출하면 안 예쁨 — 팀 코드/구역 번호만 남긴다.
# 매칭 안 되는 값(135_union 등)은 원본 그대로 통과.
def simplify_team_id(team_id):
    m = re.fullmatch(r'team_(\d+)', team_id or '')
    return m.group(1) if m else team_id


def simplify_area_id(area_id):
    m = re.fullmatch(r'area_\d+_(\d+)', area_id or '')
    return m.group(1) if m else area_id


class Command(BaseCommand):
    help = '프로덕션 USERS 중 --team-id에 해당하는 인원을 dev USERS로 복사한다.'

    def add_arguments(self, parser):
        parser.add_argument('team_id')
        parser.add_argument('--prod-url', default='http://localhost:8081')

    def handle(self, *args, **options):
        team_id = options['team_id']
        prod = DataRouterClient(url=options['prod_url'])
        dev = DataRouterClient()  # settings.DATA_ROUTER_URL (dev, :8080)

        rows = prod.query(
            """SELECT SABUN, NAME, TEAM_ID, AREA_ID, GMAIL, TELEGRAM_ID, STATUS,
                      ROLE_IDS, GOALS, CREATED_BY
                 FROM USERS
                WHERE TEAM_ID = :1 AND DELETED_AT IS NULL
                ORDER BY NAME""",
            [team_id],
        )
        self.stdout.write(f'{len(rows)} rows fetched from prod (team_id={team_id})')

        inserted = 0
        for r in rows:
            try:
                dev.exec(
                    """INSERT INTO USERS
                         (SABUN, NAME, TEAM_ID, AREA_ID, GMAIL, TELEGRAM_ID, STATUS,
                          ROLE_IDS, GOALS, CREATED_BY, UPDATED_BY)
                       VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9, :10, :10)""",
                    [
                        r['sabun'], r['name'],
                        simplify_team_id(r['team_id']), simplify_area_id(r['area_id']),
                        r['gmail'], r['telegram_id'], r['status'],
                        r['role_ids'], r['goals'], r['created_by'],
                    ],
                )
                inserted += 1
            except DataRouterError as e:
                self.stderr.write(self.style.ERROR(f'{r["sabun"]} {r["name"]}: {e.code} — {e}'))

        self.stdout.write(self.style.SUCCESS(f'{inserted}/{len(rows)} inserted into dev'))
