# services/main/src/auth/passkey.js 포팅 — 공유 패스키 sha256 해시 비교.
import hashlib
import hmac

from django.conf import settings

from api.clients.data_router import DataRouterClient


def _sha256_hex(s):
    return hashlib.sha256(str(s).encode('utf-8')).hexdigest()


def verify(passkey):
    """반환: (ok: bool, reason: str|None)"""
    if not passkey:
        return False, 'empty'
    row = DataRouterClient().query_one(
        'SELECT PASSKEY_HASH FROM AUTH_CONFIGS WHERE REGION_ID = :1',
        [settings.REGION_ID],
        cache_ttl_ms=5_000,
    )
    if not row or not row.get('passkey_hash'):
        return False, 'unconfigured'
    supplied = _sha256_hex(passkey)
    ok = hmac.compare_digest(supplied, str(row['passkey_hash']).lower())
    return (True, None) if ok else (False, 'mismatch')


def set_hash(passkey):
    # 원본은 MERGE 한 방(INSERT 절엔 REGION_ID/PASSKEY_HASH만 — 마이그레이션 시드로
    # row가 항상 존재한다고 가정). dev DB는 시드가 없어 update-then-insert로 대체.
    h = _sha256_hex(passkey)
    client = DataRouterClient()
    affected = client.exec(
        'UPDATE AUTH_CONFIGS SET PASSKEY_HASH = :1, UPDATED_AT = SYSTIMESTAMP WHERE REGION_ID = :2',
        [h, settings.REGION_ID],
    )
    if not affected:
        client.exec(
            """INSERT INTO AUTH_CONFIGS
                 (REGION_ID, PASSKEY_HASH, ACCESS_TTL, REFRESH_TTL, CREATED_BY, UPDATED_BY)
               VALUES (:1, :2, :3, :4, 'SYSTEM', 'SYSTEM')""",
            [settings.REGION_ID, h, settings.JWT_ACCESS_TTL, settings.JWT_REFRESH_TTL],
        )
