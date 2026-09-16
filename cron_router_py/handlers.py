# 잡 핸들러 레지스트리 — services/cron-router/src/cron/handlers.js 포팅.
# 실제 비즈니스 로직은 여기 없음 — main(Django)의 /internal/cron/* 를 호출만 함.
# 새 잡이 늘어나면 register()로 추가.
import logging

import config

logger = logging.getLogger('cron_router.handlers')

_HANDLERS = {}


def register(name, fn):
    _HANDLERS[name] = fn


def get(name):
    return _HANDLERS.get(name)


def names():
    return list(_HANDLERS.keys())


def make_main_cron_handler(name, path):
    """main의 /internal/cron/* 호출 표준 패턴 — 501(스텁 미구현)은 실패가 아니라
    조용히 스킵 처리(아직 안 만든 핸들러 때문에 크론 전체가 에러로 안 보이게)."""
    async def handler(ctx):
        if not config.MAIN_INTERNAL_TOKEN:
            logger.warning('%s: token missing', name)
            return {'ok': False, 'reason': 'no_token'}
        try:
            resp = await ctx['http'].post(
                f'{config.MAIN_URL}{path}',
                json=ctx.get('payload') or {},
                headers={'Authorization': f'Bearer {config.MAIN_INTERNAL_TOKEN}'},
                timeout=60.0,
            )
        except Exception as e:
            logger.error('%s failed: %s', name, e)
            return {'ok': False, 'reason': 'http_error', 'message': str(e)}

        if resp.status_code == 501:
            logger.info('%s: main stub', name)
            return {'ok': True, 'reason': 'stub'}
        if resp.status_code >= 400:
            logger.error('%s failed: status=%s body=%s', name, resp.status_code, resp.text)
            return {'ok': False, 'reason': 'http_error', 'status': resp.status_code}
        return {'ok': True, 'summary': resp.json()}
    return handler


register('sendProspectDashboard', make_main_cron_handler('sendProspectDashboard', '/internal/cron/send-prospect-dashboard'))
register('sendMatchingDashboard', make_main_cron_handler('sendMatchingDashboard', '/internal/cron/send-matching-dashboard'))
register('sendStats', make_main_cron_handler('sendStats', '/internal/cron/send-stats'))
register('sendShedUnifiedDashboard135', make_main_cron_handler('sendShedUnifiedDashboard135', '/internal/cron/send-shed-unified-dashboard'))
register('sendShedUnifiedDashboard246', make_main_cron_handler('sendShedUnifiedDashboard246', '/internal/cron/send-shed-246-dashboard'))
register('sendShedTmDashboard135', make_main_cron_handler('sendShedTmDashboard135', '/internal/cron/send-shed-tm-dashboard'))
register('sendShedTmDashboard246', make_main_cron_handler('sendShedTmDashboard246', '/internal/cron/send-shed-246-tm-dashboard'))
register('sendShedSchedDashboard135', make_main_cron_handler('sendShedSchedDashboard135', '/internal/cron/send-shed-sched-dashboard'))
register('sendShedSchedDashboard246', make_main_cron_handler('sendShedSchedDashboard246', '/internal/cron/send-shed-246-sched-dashboard'))
