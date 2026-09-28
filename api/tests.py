# shed CORS 미들웨어 동작 검증 (DB 없이 도는 최소 테스트)
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
