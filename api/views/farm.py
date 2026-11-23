# 밭 게임 — 품종(짧카 ID로 결정)과 햇살(재화) 적립·잔액 계산
import hashlib

# (키, 이름, 희귀도, 가중치) — 가중치 합 100. 키는 프론트 도트 스프라이트(farmSprites.js flower_<키>)와 맞춤.
SPECIES = [
    ('daisy', '데이지', 'common', 25), ('sunflower', '해바라기', 'common', 25), ('tulip', '튤립', 'common', 25),
    ('hydrangea', '수국', 'rare', 10), ('rose', '장미', 'rare', 10), ('goldtulip', '황금 튤립', 'legend', 5),
]
RARITY_KO = {'common': '일반', 'rare': '희귀', 'legend': '전설'}

STAGE_ORDER = ['씨앗', '새싹', '떡잎', '꽃']
# 떡잎은 반장 재가(사람 확인)를 거치는 단계라 크게, 혼자 채우는 단계는 작게(기획서 어뷰징 방지)
STAGE_REWARD = {'씨앗': 1, '새싹': 3, '떡잎': 10, '꽃': 10}


def plant_species(card_id):
    """짧카 ID(무작위 UUID)의 해시로 품종을 정함 — 심을 때 뽑힌 품종이 DB 컬럼 없이 언제나 같음."""
    n = int(hashlib.md5(str(card_id).encode()).hexdigest()[:8], 16) % 100
    for key, name, rarity, weight in SPECIES:
        if n < weight:
            return {'key': key, 'name': name, 'rarity': rarity, 'rarityLabel': RARITY_KO[rarity]}
        n -= weight
    raise AssertionError('SPECIES 가중치 합이 100이 아님')


def missing_stage_rewards(cards, sabun, got):
    """내 짧카가 도달한 단계 중 아직 안 받은 보상 [(reason, card_id, amount)] — 꽃이면 씨앗~꽃 전부(소급 포함)."""
    out = []
    for c in cards:
        if c['member_id'] != sabun or c.get('stage') not in STAGE_ORDER:
            continue
        for st in STAGE_ORDER[:STAGE_ORDER.index(c['stage']) + 1]:
            if (f'stage_{st}', c['short_card_id']) not in got:
                out.append((f'stage_{st}', c['short_card_id'], STAGE_REWARD[st]))
    return out


def _balance(client, sabun):
    row = client.query_one("SELECT NVL(SUM(AMOUNT), 0) AS TOTAL FROM FARM_SUNSHINE_LOG WHERE MEMBER_ID = :1", [sabun])
    return int(row['total']) if row else 0


def award_stage_sunshine(client, sabun, cards):
    """단계 보상 적립 후 (잔액, 이번에 늘어난 양). 같은 보상은 (MEMBER_ID, REASON, REF_ID) 유니크로 한 번만."""
    logs = client.query("SELECT REASON, REF_ID, AMOUNT FROM FARM_SUNSHINE_LOG WHERE MEMBER_ID = :1", [sabun], fetch_limit=20000)
    before = sum(int(r['amount']) for r in logs)
    todo = missing_stage_rewards(cards, sabun, {(r['reason'], r['ref_id']) for r in logs})
    if not todo:
        return before, 0
    inserted = 0
    for i in range(0, len(todo), 100):
        chunk = todo[i:i + 100]
        selects, args = [], []
        for j, (reason, ref_id, amount) in enumerate(chunk):
            selects.append(f'SELECT RAWTOHEX(SYS_GUID()), :{j * 4 + 1}, :{j * 4 + 2}, :{j * 4 + 3}, :{j * 4 + 4} FROM DUAL')
            args += [sabun, reason, ref_id, amount]
        # 동시에 두 번 열려도 중복 행은 조용히 건너뜀
        inserted += client.exec(
            f"""INSERT /*+ IGNORE_ROW_ON_DUPKEY_INDEX(FARM_SUNSHINE_LOG, UQ_FARM_SUNSHINE) */
                INTO FARM_SUNSHINE_LOG (LOG_ID, MEMBER_ID, REASON, REF_ID, AMOUNT)
                {' UNION ALL '.join(selects)}""",
            args,
        )
    if inserted == len(todo):
        gained = sum(a for _, _, a in todo)
        return before + gained, gained
    after = _balance(client, sabun)   # 다른 요청이 일부를 먼저 넣음 — 실제 잔액으로 다시 계산
    return after, max(after - before, 0)
