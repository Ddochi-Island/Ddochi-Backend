# 합당한 자 통화 중·접속자 상태 — 프로세스 메모리 dict. Django(gunicorn 2워커)에 있을 땐 워커마다 따로 들고 있어서
# 표시가 갈라졌음 → 한 프로세스인 tel_router로 옮김. DB 없이(재시작하면 비워짐 — 하트비트로 몇 초 안에 다시 채워짐).
import time

CALL_TTL_S = 60       # 통화 중 표시 — 거는 사람 화면의 상태 확인(3.5초마다)이 끊기면 60초 뒤 자동 해제
PRESENCE_TTL_S = 12   # 접속자 — 12초 동안 상태 확인이 없으면 나간 걸로

calls = {}     # prospectId → {callerName, callerSabun, startedAt, lastHeartbeat}
presence = {}  # sabun → {name, lastHeartbeat}


def handle(op, sabun=None, name=None, prospect_id=None, calling_id=None, now=None):
    now = time.time() if now is None else now
    if op == 'start':
        calls[prospect_id] = {'callerName': name, 'callerSabun': sabun, 'startedAt': now}
    elif op == 'end':
        calls.pop(prospect_id, None)
    elif op == 'leave':
        presence.pop(sabun, None)
    elif op == 'status':
        if calling_id and calling_id in calls:
            calls[calling_id]['lastHeartbeat'] = now
        for pid in list(calls):
            if now - (calls[pid].get('lastHeartbeat') or calls[pid]['startedAt']) > CALL_TTL_S:
                del calls[pid]
        if sabun:
            presence[sabun] = {'name': name, 'lastHeartbeat': now}
        for s in list(presence):
            if now - presence[s]['lastHeartbeat'] > PRESENCE_TTL_S:
                del presence[s]
        return {'calls': calls, 'presence': presence}
    else:
        raise ValueError(op)
    return {}


if __name__ == '__main__':  # python presence.py — 자체 점검
    handle('start', 'A', '가', 'P1', now=0)
    assert handle('status', 'B', '나', now=1)['calls']['P1']['callerSabun'] == 'A'
    handle('status', 'A', '가', calling_id='P1', now=50)            # 거는 사람 하트비트
    assert 'P1' in handle('status', now=100)['calls']                # 50초 뒤 하트비트 기준 아직 살아 있음
    assert 'P1' not in handle('status', now=111)['calls']            # 하트비트 끊기고 60초 지나면 해제
    assert set(handle('status', 'C', '다', now=111)['presence']) == {'C'}  # A·B는 12초 넘게 안 와서 빠짐
    handle('leave', 'C')
    assert handle('status', now=112)['presence'] == {}
    handle('start', 'A', '가', 'P2', now=200); handle('end', prospect_id='P2')
    assert handle('status', now=201)['calls'] == {}
    print('ok')
