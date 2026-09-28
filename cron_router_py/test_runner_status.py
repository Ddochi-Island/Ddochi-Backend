# runner._failure_reason 검증 — 핸들러가 예외 없이 실패를 돌려줘도 실패로 기록되는지
from runner import _failure_reason

assert _failure_reason({'ok': True, 'summary': {'success': True, 'results': {'1': {'sent': True}, '2': {'skipped': True}}}}) is None
assert _failure_reason({'ok': True, 'reason': 'stub'}) is None
assert _failure_reason({'ok': False, 'reason': 'http_error', 'status': 500}) == 'http_error 500'
assert _failure_reason({'ok': False, 'reason': 'no_token'}) == 'no_token'
assert _failure_reason({'ok': True, 'summary': {'results': {'1': {'sent': True}, '3': {'sent': False}, '5': {'error': 'x'}}}}) == 'send failed: 3,5'
print('runner status tests OK')
