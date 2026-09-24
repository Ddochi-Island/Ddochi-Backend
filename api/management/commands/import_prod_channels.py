# 프로덕션 BROADCAST_SETTINGS(BROADCAST_TYPE='prospect_chat').CONFIG의
# *ChatId/*ChatTitle 필드들 → dev BROADCAST_SETTINGS.CONFIG로 임포트.
# TEAM_CHANNELS 테이블은 레거시에서 실제로 안 씀(0 rows) — 진짜 채널 연결은
# BROADCAST_SETTINGS.CONFIG에 직접 들어있음(v2와 동일 구조). telegram_pair.py의
# CHANNEL_DEFS를 그대로 재사용해서 어떤 필드가 "채널 연결"인지 판단한다 —
# cronJobs/lastMsgId/pinnedMsgId 등 나머지 운영 상태는 일부러 안 옮김(v2가
# 자체적으로 새로 관리). 프로덕션 쪽은 SELECT만 사용 — 절대 쓰기 안 함.
# patch_team_config가 JSON_MERGEPATCH라 재실행해도 안전(idempotent).
import json
import re

from django.core.management.base import BaseCommand

from api.clients.data_router import DataRouterClient, DataRouterError
from api.telegram.team_config import patch_team_config
from api.views.telegram_pair import CHANNEL_DEFS

_UNION_RE = re.compile(r'(\d+)_union')


def normalize_team_id(team_id):
    m = _UNION_RE.fullmatch(team_id)
    if m:
        return f'{m.group(1)} 연합'
    if team_id.startswith('team_'):
        return team_id[len('team_'):]
    return team_id


class Command(BaseCommand):
    help = '프로덕션 BROADCAST_SETTINGS(prospect_chat)의 채널 연결 필드를 dev로 임포트한다.'

    def add_arguments(self, parser):
        parser.add_argument('--prod-url', default='http://localhost:8081')

    def handle(self, *args, **options):
        prod = DataRouterClient(url=options['prod_url'])
        dev = DataRouterClient()  # settings.DATA_ROUTER_URL (dev, :8080)

        rows = prod.query(
            "SELECT TEAM_ID, CONFIG FROM BROADCAST_SETTINGS WHERE BROADCAST_TYPE = 'prospect_chat'"
        )
        self.stdout.write(f'{len(rows)} teams fetched from prod BROADCAST_SETTINGS(prospect_chat)')

        applied_teams = 0
        applied_fields = 0
        for r in rows:
            try:
                cfg = json.loads(r['config']) if r['config'] else {}
            except (TypeError, ValueError):
                cfg = {}

            patch = {}
            for defn in CHANNEL_DEFS.values():
                field = defn['field']  # e.g. 'prospectChatId'
                if not field.endswith('ChatId'):
                    continue
                chat_id = cfg.get(field)
                if not chat_id:
                    continue
                patch[field] = chat_id
                title_field = field[:-len('Id')] + 'Title'  # prospectChatId -> prospectChatTitle
                if cfg.get(title_field):
                    patch[title_field] = cfg[title_field]

            if not patch:
                continue

            team_id = normalize_team_id(r['team_id'])
            try:
                patch_team_config(dev, team_id, patch, 'SYSTEM')
                applied_teams += 1
                applied_fields += len(patch)
                self.stdout.write(f'{r["team_id"]} -> {team_id}: {sorted(patch.keys())}')
            except DataRouterError as e:
                self.stderr.write(self.style.ERROR(f'{team_id}: {e.code} — {e}'))

        self.stdout.write(self.style.SUCCESS(
            f'{applied_teams} teams applied, {applied_fields} fields total, {len(rows)} teams total from prod'
        ))
