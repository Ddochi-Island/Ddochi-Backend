# hmac_verify.py 자체 검증 — Node lib/callbackHmac.js와 같은 포맷인지 확인하는 최소 self-check
from hmac_verify import _compute_hmac, verify_callback_data

SECRET = 'test-secret'
NOW = 1000000000000

sig = _compute_hmac(SECRET, 'hj', 'abc.a', NOW, 12345)
assert len(sig) == 11, sig

data = f'hj|abc.a|{NOW}|{sig}'
ok = verify_callback_data(SECRET, data, 12345, 600_000, now=NOW)
assert ok == {'ok': True, 'action': 'hj', 'args': 'abc.a', 'ts': NOW}, ok

# 다른 chat_id로 재생하면 실패해야 함
bad_chat = verify_callback_data(SECRET, data, 99999, 600_000, now=NOW)
assert bad_chat['ok'] is False and bad_chat['reason'] == 'hmac_mismatch', bad_chat

# 시간창 밖이면 실패해야 함
expired = verify_callback_data(SECRET, data, 12345, 600_000, now=NOW + 700_000)
assert expired['ok'] is False and expired['reason'] == 'ts_expired', expired

print('ok')
