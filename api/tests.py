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

    def test_helpers_carried_with_sabun_and_name_fallback(self):
        # 추첨 낙첨자(조력자): 사번 있으면 그대로, 'existing' placeholder면 이름으로 MEMBERS 조회
        payload = {**self.BASE, 'env': '무난', 'introducer': '당첨', 'introducerSabun': 'S1',
                   'helperNames': ['낙첨A', '낙첨B'], 'helperSabuns': ['S2', 'existing']}
        r, client = self._post(payload, [None, {'member_id': 'S3'}])
        self.assertEqual(r.status_code, 200)
        args = client.exec.call_args[0][1]
        self.assertIn('S1', args)
        self.assertIn('S2, S3', args)


class DailyReportErrorTests(SimpleTestCase):
    def test_unexpected_exception_returns_readable_message(self):
        # 빈 알림창 방지: 예상 못 한 예외도 {success:false, message}로 내려가야 함
        client = MagicMock()
        client.query_one.side_effect = RuntimeError('boom')
        with patch('api.auth.gate.auth_jwt.verify', return_value={'sabun': 'S1'}), \
                patch('api.views.daily_report.DataRouterClient', return_value=client):
            r = self.client.post('/api/daily-report', data=json.dumps({'name': '홍길동'}),
                                 content_type='application/json', HTTP_AUTHORIZATION='Bearer x')
        self.assertEqual(r.status_code, 500)
        self.assertFalse(r.json()['success'])
        self.assertIn('boom', r.json()['message'])


class TeacherAssignTests(SimpleTestCase):
    ROW = {'sarang_id': 'SID', 'name': '최지수', 'hab_jae_yang_id': 'HJ1'}

    def _run(self, raw, query_results):
        from api.views.internal_telegram import _assign_teacher
        client = MagicMock()
        client.query_one.side_effect = query_results
        with patch('api.views.internal_telegram.refresh_matching_dashboard_for_sarang') as refresh:
            return _assign_teacher(client, 'EF420476', raw), client, refresh

    def test_success_updates_teacher_and_refreshes_dashboard(self):
        res, client, refresh = self._run('김교사', [self.ROW, {'member_id': 'T1'}])
        self.assertTrue(res['ok'])
        self.assertEqual(client.exec.call_args[0][1], ['T1', None, 'HJ1'])
        refresh.assert_called_once()

    def test_other_region_teacher_stored_as_override(self):
        res, client, _ = self._run('이명훈(타지역)', [self.ROW])
        self.assertTrue(res['ok'])
        self.assertEqual(client.exec.call_args[0][1], [None, '이명훈(타지역)', 'HJ1'])

    def test_unknown_teacher_name_changes_nothing(self):
        res, client, refresh = self._run('없는사람', [self.ROW, None])
        self.assertFalse(res['ok'])
        client.exec.assert_not_called()
        refresh.assert_not_called()

    def test_unknown_short_code_changes_nothing(self):
        res, client, _ = self._run('김교사', [None])
        self.assertFalse(res['ok'])
        client.exec.assert_not_called()
