# 프로덕션 ROLES 전체를 dev DB로 복사. 프로덕션 쪽은 SELECT만 사용 — 절대 쓰기 안 함.
from django.core.management.base import BaseCommand

from api.clients.data_router import DataRouterClient, DataRouterError


class Command(BaseCommand):
    help = '프로덕션 ROLES(전체)를 dev ROLES로 복사한다.'

    def add_arguments(self, parser):
        parser.add_argument('--prod-url', default='http://localhost:8081')

    def handle(self, *args, **options):
        prod = DataRouterClient(url=options['prod_url'])
        dev = DataRouterClient()  # settings.DATA_ROUTER_URL (dev, :8080)

        rows = prod.query(
            """SELECT ROLE_ID, NAME, SCOPE, PERMISSIONS, CREATED_BY
                 FROM ROLES
                WHERE DELETED_AT IS NULL
                ORDER BY SCOPE, NAME"""
        )
        self.stdout.write(f'{len(rows)} roles fetched from prod')

        inserted = 0
        for r in rows:
            try:
                dev.exec(
                    """INSERT INTO ROLES (ROLE_ID, NAME, SCOPE, PERMISSIONS, CREATED_BY, UPDATED_BY)
                       VALUES (:1, :2, :3, :4, :5, :5)""",
                    [r['role_id'], r['name'], r['scope'], r['permissions'], r['created_by']],
                )
                inserted += 1
            except DataRouterError as e:
                self.stderr.write(self.style.ERROR(f'{r["role_id"]}: {e.code} — {e}'))

        self.stdout.write(self.style.SUCCESS(f'{inserted}/{len(rows)} inserted into dev'))
