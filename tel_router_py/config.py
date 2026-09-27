# 환경변수 기반 설정값 모음 — 원본 tel_router(Node)와 동일한 이름을 그대로 씀
import os

from dotenv import load_dotenv

load_dotenv()

PORT = int(os.getenv('PORT', '8090'))

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_API_BASE = os.getenv('TELEGRAM_API_BASE', 'https://api.telegram.org')

# L1 — Telegram이 웹훅마다 X-Telegram-Bot-Api-Secret-Token으로 그대로 돌려줌.
WEBHOOK_SECRET = os.getenv('TG_WEBHOOK_SECRET', '')

# main(Django) → tel_router로 발송 요청을 보낼 때 쓰는 시크릿 (X-Enqueue-Secret).
ENQUEUE_SECRET = os.getenv('ENQUEUE_SECRET', '')

# tel_router → main(Django) /internal/telegram/pair-complete, /internal/telegram/callback 호출용.
MAIN_SERVER_URL = os.getenv('MAIN_SERVER_URL', '').rstrip('/')
MAIN_INTERNAL_TELEGRAM_TOKEN = os.getenv('MAIN_INTERNAL_TELEGRAM_TOKEN', '')

# L3 — 인라인 버튼 callback_data HMAC. main의 TG_CALLBACK_HMAC_SECRET과 동일해야 함.
CALLBACK_HMAC_SECRET = os.getenv('TG_CALLBACK_HMAC_SECRET', '')
# 카드 자체는 정각 크론(1시간 주기)/이벤트 때만 재생성되는데 기본값 10분은 그
# 사이 텀보다 훨씬 짧아서 며칠 지난 카드는 거의 항상 "만료된 버튼"으로 뜸
# (2026-09-27 실사용자 신고 — 25일에 뜬 카드를 27일에 눌렀더니 만료됨). 7일로 늘림.
CALLBACK_TS_WINDOW_MS = int(os.getenv('TG_CALLBACK_TS_WINDOW_MS', str(7 * 24 * 3600_000)))
