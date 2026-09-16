# 환경변수 기반 설정값 모음 — 원본 cron-router(Node)와 동일한 이름을 그대로 씀
import os

from dotenv import load_dotenv

load_dotenv()

PORT = int(os.getenv('PORT', '8083'))
CRON_SECRET = os.getenv('CRON_SECRET', '')
SELF_TICK = os.getenv('SELF_TICK', '1') != '0'
TICK_INTERVAL_MS = int(os.getenv('TICK_INTERVAL_MS', str(10 * 60 * 1000)))
LOOKBACK_WINDOW_MS = int(os.getenv('LOOKBACK_WINDOW_MS', str(60 * 60 * 1000)))
MIN_JOB_INTERVAL_MS = int(os.getenv('MIN_JOB_INTERVAL_MS', '30000'))

DATA_ROUTER_URL = os.getenv('DATA_ROUTER_URL', 'http://localhost:8080').rstrip('/')
DATA_ROUTER_TOKEN = os.getenv('DATA_ROUTER_TOKEN', '')
DATA_ROUTER_CALLER = os.getenv('DATA_ROUTER_CALLER', 'cron_router')

# main(Django, Ddochi-Backend)의 /internal/cron/* 호출용.
MAIN_URL = os.getenv('MAIN_URL', 'http://127.0.0.1:8000').rstrip('/')
MAIN_INTERNAL_TOKEN = os.getenv('MAIN_INTERNAL_TELEGRAM_TOKEN') or os.getenv('MAIN_INTERNAL_TOKEN', '')
