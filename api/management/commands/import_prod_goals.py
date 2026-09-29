# 실서버(레거시) BROADCAST_SETTINGS.telegram_goals(지역별 목표)를 v2로 옮기는 일회성 커맨드 — 프로덕션은 SELECT만
# 레거시는 team_1↔team_5 표시 이름이 바뀌어 있어서(team_1='5팀', team_5='1팀') TEAM_ID 번호가 아니라 표시 이름의
# 숫자로 v2 REGION_CODE를 정함 — 회원 대조로 확인(2026-09-30: team_5 회원 82명이 v2 1지역, team_1 회원 76명이 5지역).
# 구역 키('N구역')는 v2 area_key()와 같은 형식이라 그대로 씀. --dry-run으로 먼저 확인 권장.
import json
import re

from django.core.management.base import BaseCommand

from api.clients.data_router import DataRouterClient
from api.telegram.team_goals import load_team_goals, save_team_goals


class Command(BaseCommand):
    help = '레거시 지역별 목표(telegram_goals)를 v2 BROADCAST_SETTINGS로 옮긴다.'

    def add_arguments(self, parser):
        parser.add_argument('--prod-url', default='http://localhost:8081')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--overwrite', action='store_true', help='v2에 이미 목표가 있어도 덮어씀')

    def handle(self, *args, **options):
        prod = DataRouterClient(url=options['prod_url'], timeout_ms=60000)
        dev = DataRouterClient()
        names = {r['team_id']: r['display_name'] for r in prod.query('SELECT TEAM_ID, DISPLAY_NAME FROM TEAMS')}
        rows = prod.query(
            "SELECT TEAM_ID, CONFIG FROM BROADCAST_SETTINGS WHERE BROADCAST_TYPE = 'telegram_goals' AND DELETED_AT IS NULL"
        )
        for r in rows:
            m = re.fullmatch(r'(\d+)팀', names.get(r['team_id']) or '')
            if not m:
                self.stdout.write(f"건너뜀 {r['team_id']}({names.get(r['team_id'])}): 지역 번호 없음")
                continue
            region = m.group(1)
            goals = json.loads(r['config'] or '{}')
            existing = load_team_goals(dev, region)
            action = '덮어씀' if existing else '새로 저장'
            if existing and not options['overwrite']:
                action = '건너뜀(v2에 이미 있음, --overwrite로 덮어쓰기)'
            self.stdout.write(f"{r['team_id']}({names[r['team_id']]}) → v2 {region}지역: 구역 {len(goals) - ('Total' in goals)}개, "
                              f"Total {goals.get('Total')} — {action}")
            if options['dry_run'] or action.startswith('건너뜀'):
                continue
            save_team_goals(dev, region, goals, 'import_prod')
        if options['dry_run']:
            self.stdout.write(self.style.WARNING('--dry-run: 아무것도 쓰지 않음'))
