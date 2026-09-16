# pairing.py의 /pair 명령 파서에 대한 최소 self-check
from pairing import is_pair_command, parse_pair_code

assert is_pair_command('/pair A1B2C3D4')
assert is_pair_command('/pair@my_bot A1B2C3D4')
assert not is_pair_command('hello')

assert parse_pair_code('/pair A1B2C3D4') == 'A1B2C3D4'
assert parse_pair_code('/pair@my_bot a1b2c3d4') == 'A1B2C3D4'
assert parse_pair_code('/pair') is None
assert parse_pair_code('/pair  ') is None
assert parse_pair_code('/pair too many words') is None

print('ok')
