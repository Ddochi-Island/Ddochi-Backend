# sql/*.sql 파일을 세미콜론 기준으로 잘라 data_router 경유로 순서대로 실행.
from django.core.management.base import BaseCommand, CommandError

from api.clients.data_router import DataRouterClient, DataRouterError


class Command(BaseCommand):
    help = 'sql/*.sql 파일의 문장을 하나씩 data_router.exec()로 실행한다 (DDL/시드용).'

    def add_arguments(self, parser):
        parser.add_argument('path', help='실행할 .sql 파일 경로')

    def handle(self, *args, **options):
        path = options['path']
        try:
            with open(path, encoding='utf-8') as f:
                sql = f.read()
        except OSError as e:
            raise CommandError(f'{path} 읽기 실패: {e}')

        # 줄 단위로 -- 주석을 먼저 걷어낸 뒤 세미콜론으로 문장을 나눈다.
        # (주석이 앞에 붙은 채로 나누면 첫 문장 전체가 주석으로 오인될 수 있음)
        no_comments = '\n'.join(
            line for line in sql.splitlines() if not line.strip().startswith('--')
        )
        statements = [s.strip() for s in no_comments.split(';')]
        statements = [s for s in statements if s]

        client = DataRouterClient()
        for stmt in statements:
            preview = ' '.join(stmt.split())[:80]
            try:
                client.exec(stmt)
                self.stdout.write(self.style.SUCCESS(f'ok: {preview}'))
            except DataRouterError as e:
                self.stderr.write(self.style.ERROR(f'{e.code}: {preview} — {e}'))
                raise SystemExit(1)
