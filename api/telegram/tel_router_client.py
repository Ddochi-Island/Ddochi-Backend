# tel_router_py에 텔레그램 발송을 요청하는 HTTP 클라이언트 — POST /enqueue 하나만 씀
import requests
from django.conf import settings


def enqueue(method, payload, await_result=False, timeout=12):
    url = f"{settings.TEL_ROUTER_URL.rstrip('/')}/enqueue"
    headers = {'X-Enqueue-Secret': settings.TEL_ROUTER_ENQUEUE_SECRET}
    body = {'method': method, 'payload': payload}
    if await_result:
        body['awaitResult'] = True
    resp = requests.post(url, json=body, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return data.get('result') if await_result else data
