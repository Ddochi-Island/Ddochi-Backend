# shed 연동 검증 — CORS 미들웨어 + shed-webhook 페이로드 분기 (DB 없이 도는 최소 테스트)
import json
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

ALLOWED = 'https://shed-event.vercel.app'


@override_settings(CORS_ALLOWED_ORIGINS=[ALLOWED])
class ShedCorsTests(SimpleTestCase):
    def test_preflight_allowed_origin(self):
        r = self.client.options(
            '/api/shed/users', HTTP_ORIGIN=ALLOWED,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET', HTTP_ACCESS_CONTROL_REQUEST_HEADERS='x-shed-key',
        )
        self.assertEqual(r.status_code, 204)
        self.assertEqual(r['Access-Control-Allow-Origin'], ALLOWED)
        self.assertIn('X-Shed-Key', r['Access-Control-Allow-Headers'])

    def test_preflight_disallowed_origin(self):
        r = self.client.options('/api/shed/users', HTTP_ORIGIN='https://evil.example')
        self.assertEqual(r.status_code, 403)
        self.assertNotIn('Access-Control-Allow-Origin', r)

    def test_actual_request_gets_cors_header(self):
        r = self.client.get('/api/shed/users', HTTP_ORIGIN=ALLOWED, HTTP_X_SHED_KEY='bogus')
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r['Access-Control-Allow-Origin'], ALLOWED)

    def test_other_paths_untouched(self):
        r = self.client.options('/api/shed-webhook', HTTP_ORIGIN=ALLOWED)
        self.assertNotIn('Access-Control-Allow-Origin', r)


@override_settings(SHED_INTERNAL_KEY='k')
class ShedWebhookTests(SimpleTestCase):
    BASE = {'name': '홍길동', 'phone': '010-1234-5678', 'age': 22, 'event': '2', 'region': '수원', 'rest': '휴식'}

    def _post(self, payload, query_one_results):
        client = MagicMock()
        client.query_one.side_effect = query_one_results
        with patch('api.views.assets.DataRouterClient', return_value=client):
            r = self.client.post('/api/shed-webhook', data=json.dumps(payload),
                                 content_type='application/json', HTTP_X_SHED_KEY='k')
        return r, client

    def test_transfer_payload_inserted_as_submitted(self):
        # GAS의 이관하기 페이로드(type 없음 + env/introducer) → 바로 submitted, 유입자는 이름으로 사번 조회
        payload = {**self.BASE, 'env': '무난', 'reaction': '좋음', 'introducer': '김유입',
                   'tmLocation': '강남역', 'tmDatetime': '2026-10-01T15:00'}
        r, client = self._post(payload, [None, {'member_id': 'M1'}])
        self.assertEqual(r.status_code, 200)
        args = client.exec.call_args[0][1]
        self.assertIn('submitted', args)
        self.assertIn('무난', args)
        self.assertIn('M1', args)

    def test_plain_application_stays_pending(self):
        r, client = self._post(self.BASE, [None])
        self.assertEqual(r.status_code, 200)
        args = client.exec.call_args[0][1]
        self.assertIn('pending', args)
        self.assertNotIn('submitted', args)

    def test_duplicate_is_skipped(self):
        r, client = self._post({**self.BASE, 'env': '무난'}, [{'intake_id': 'X'}])
        self.assertEqual(r.json()['skipped'], True)
        client.exec.assert_not_called()
