# data_router 연결 확인용 스모크 테스트: ping + 간단한 쿼리 실행.
from django.core.management.base import BaseCommand

from api.clients.data_router import DataRouterClient, DataRouterError


class Command(BaseCommand):
    help = 'data_router에 ping을 보내고 SELECT SYSDATE FROM DUAL 을 실행해 연결을 확인한다.'

    def handle(self, *args, **options):
        client = DataRouterClient()
        try:
            client.ping()
            self.stdout.write(self.style.SUCCESS(f'ping ok — {client.url}'))
            rows = client.query('SELECT SYSDATE FROM DUAL')
            self.stdout.write(self.style.SUCCESS(f'query ok — {rows}'))
        except DataRouterError as e:
            self.stderr.write(self.style.ERROR(f'{e.code}: {e}'))
            raise SystemExit(1)
