# 지역원 추천 코드 — 사번을 HMAC으로 가려서 PIONEER /event 링크에 실음.
# 설계: docs/REFERRAL_CODE.md. 별도 테이블 없이 MEMBERS를 읽어 역산 매칭한다.
import base64
import hashlib
import hmac

from decouple import config

from api.clients.data_router import DataRouterClient

CODE_LENGTH = 16


def referral_code(member_id, secret=None):
    secret = secret or config('REFERRAL_SECRET')
    digest = hmac.new(secret.encode(), member_id.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip('=')[:CODE_LENGTH]


def resolve_referral_codes(codes, secret=None):
    """코드들 → {코드: {'name', 'region'}} — PIONEER /admin 표처럼 여러 개를 한 번에 풀 때 MEMBERS를 한 번만 읽음.
    매칭 없는 코드는 결과에 없음. 사번은 돌려주지 않음(문서의 사번 비노출 원칙)."""
    wanted = {c for c in codes if c}
    if not wanted:
        return {}
    secret = secret or config('REFERRAL_SECRET')
    members = DataRouterClient().query(
        """SELECT m.MEMBER_ID, m.NAME, mah.REGION_CODE
             FROM MEMBERS m
             LEFT JOIN MEMBER_AFFILIATION_HISTORIES mah ON mah.MEMBER_ID = m.MEMBER_ID AND mah.IS_CURRENT = 1
            WHERE m.DELETED_AT IS NULL"""
    )
    out = {}
    for m in members:
        code = referral_code(m['member_id'], secret)
        if code in wanted:
            out[code] = {'name': m['name'], 'region': m['region_code']}
    return out


def resolve_referral_code(code, secret=None):
    """코드 하나 → {'name', 'region'}. 매칭 없으면 None."""
    return resolve_referral_codes([code], secret).get(code)
