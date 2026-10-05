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

    def test_dash_clears_teacher(self):
        res, client, refresh = self._run('-', [self.ROW])
        self.assertTrue(res['ok'])
        self.assertIn('해제', res['message'])
        self.assertEqual(client.exec.call_args[0][1], [None, None, 'HJ1'])
        refresh.assert_called_once()


class ProspectDashboardDateTests(SimpleTestCase):
    def test_group_by_written_date_pulled_within_3_days_of_match(self):
        from datetime import date
        from api.telegram.prospect_dashboard import _display_date
        today = date(2026, 9, 28)
        # 작성 9/25, 매칭 9/27(2일 뒤) → 작성일 그대로
        self.assertEqual(_display_date({'hj_date': '2026-09-25', 'mt_date': '2026-09-27'}, today), date(2026, 9, 25))
        # 작성 9/25, 매칭 9/28(정확히 3일 뒤) → 작성일 그대로
        self.assertEqual(_display_date({'hj_date': '2026-09-25', 'mt_date': '2026-09-28'}, today), date(2026, 9, 25))
        # 작성 9/22, 매칭 9/30(8일 뒤) → 매칭 3일 전 9/27
        self.assertEqual(_display_date({'hj_date': '2026-09-22', 'mt_date': '2026-09-30'}, today), date(2026, 9, 27))
        # 매칭 날짜 없음 → 작성일
        self.assertEqual(_display_date({'hj_date': '2026-09-22', 'mt_date': None}, today), date(2026, 9, 22))

    def test_approved_kept_two_days_after_approval(self):
        from datetime import date
        from api.telegram.prospect_dashboard import _approved_expired
        cutoff = date(2026, 9, 26)
        old_find = date(2026, 9, 23)
        self.assertFalse(_approved_expired({'approval_status': 'approved', 'appr_date': '2026-09-28'}, old_find, cutoff))
        self.assertTrue(_approved_expired({'approval_status': 'approved', 'appr_date': '2026-09-25'}, old_find, cutoff))
        self.assertTrue(_approved_expired({'approval_status': 'approved', 'appr_date': None}, old_find, cutoff))
        self.assertFalse(_approved_expired({'approval_status': 'pending', 'appr_date': None}, old_find, cutoff))


class TruncTests(SimpleTestCase):
    def test_char_columns_keep_full_korean_length(self):
        from api.views.assets import _trunc, _trunc_chars
        text = '가' * 100
        self.assertEqual(len(_trunc_chars(text, 100)), 100)   # 100 CHAR 컬럼 → 100자 그대로
        self.assertEqual(len(_trunc(text, 100)), 33)           # 바이트 기준이면 33자로 잘리던 문제
        self.assertEqual(_trunc_chars(None, 100), None)
        self.assertLessEqual(len(_trunc('가' * 200, 255).encode('utf-8')), 255)  # 바이트 컬럼(ETC)은 여전히 바이트 한도

    def test_etc_allows_1000_korean_chars(self):
        from api.views.assets import _trunc_chars
        self.assertEqual(len(_trunc_chars('가' * 1200, 1000)), 1000)


class GroupLeadScopeTests(SimpleTestCase):
    def test_widest_tier_wins_for_concurrent_positions(self):
        from api.views.short_card import _tier_rank
        self.assertEqual(min(['area_lead', 'group_lead'], key=_tier_rank), 'group_lead')
        self.assertEqual(min(['group_lead', 'team_evangelist'], key=_tier_rank), 'team_evangelist')
        self.assertEqual(min(['general', 'sub_area_lead'], key=_tier_rank), 'sub_area_lead')

    def test_group_scope_covers_group_districts(self):
        from api.views.short_card import _scope_sql
        sql, args = _scope_sql({'position_code': 'group_lead', 'region_code': '3', 'district_code': '2',
                                'group_districts': ['1', '2', '3']}, 'S')
        self.assertIn('DISTRICT_CODE IN (:2, :3, :4)', sql)
        self.assertEqual(args, ['3', '1', '2', '3'])

    def test_group_lead_without_group_sees_nothing_extra(self):
        from api.views.short_card import _scope_sql
        sql, args = _scope_sql({'position_code': 'group_lead', 'region_code': '3', 'district_code': None,
                                'group_districts': []}, 'S')
        self.assertEqual(args, ['3', '__none__'])


class SproutApprovalTests(SimpleTestCase):
    FULL = {'gender': '남', 'age': '22', 'relation': 'x', 'phone': 'x', 'residence': 'x', 'school_major': 'x',
            'personality': 'x', 'hobby': 'x', 'has_partner': 'x', 'family_relation': 'x', 'environment': 'x',
            'desired_image': 'x', 'recent_concern': 'x', 'family_atmosphere': 'x', 'human_relations': 'x'}

    def test_stage3_needs_approval_to_be_sprout(self):
        from api.views.short_card import _journal_stage
        self.assertEqual(_journal_stage({**self.FULL, 'sprout_status': None}), '새싹')
        self.assertEqual(_journal_stage({**self.FULL, 'sprout_status': 'pending'}), '새싹')
        self.assertEqual(_journal_stage({**self.FULL, 'sprout_status': 'approved'}), '떡잎')
        self.assertEqual(_journal_stage({**self.FULL, 'human_relations': None, 'sprout_status': 'approved'}), '새싹')

    def test_who_can_decide_sprout(self):
        from api.views.short_card import _can_decide_sprout
        lead = {'position_code': 'group_lead', 'region_code': '3', 'group_districts': ['1', '2']}
        self.assertTrue(_can_decide_sprout(lead, '3', '2'))
        self.assertFalse(_can_decide_sprout(lead, '3', '4'))   # 다른 반 구역
        self.assertFalse(_can_decide_sprout(lead, '5', '1'))   # 다른 지역
        self.assertTrue(_can_decide_sprout({'position_code': 'team_evangelist', 'region_code': '3', 'group_districts': []}, '3', '4'))
        self.assertFalse(_can_decide_sprout({'position_code': 'area_lead', 'region_code': '3', 'group_districts': []}, '3', '1'))
        self.assertTrue(_can_decide_sprout({'position_code': 'admin', 'region_code': None, 'group_districts': []}, '6', '1'))


class ReferralCodeTests(SimpleTestCase):
    def test_code_is_stable_16_chars_and_secret_dependent(self):
        from api.util.referral import referral_code
        a = referral_code('10001', 'secret-a')
        self.assertEqual(a, referral_code('10001', 'secret-a'))
        self.assertEqual(len(a), 16)
        self.assertNotIn('10001', a)
        self.assertNotEqual(a, referral_code('10001', 'secret-b'))
        self.assertNotEqual(a, referral_code('10002', 'secret-a'))

    def test_batch_resolve_matches_without_member_id(self):
        from api.util import referral
        rows = [{'member_id': '10001', 'name': '홍길동', 'region_code': '3'},
                {'member_id': '10002', 'name': '김철수', 'region_code': '6'}]
        code = referral.referral_code('10002', 's')
        with patch.object(referral, 'DataRouterClient') as dr:
            dr.return_value.query.return_value = rows
            out = referral.resolve_referral_codes([code, 'nomatch', ''], 's')
        self.assertEqual(out, {code: {'name': '김철수', 'region': '6'}})

    @override_settings(PIONEER_INTERNAL_KEY='k')
    def test_resolve_endpoint_requires_key(self):
        r = self.client.post('/api/referral/resolve', data=json.dumps({'codes': ['x']}), content_type='application/json')
        self.assertEqual(r.status_code, 401)
        r = self.client.post('/api/referral/resolve', data=json.dumps({'codes': ['x']}),
                             content_type='application/json', HTTP_X_PIONEER_KEY='wrong')
        self.assertEqual(r.status_code, 401)


class SproutDeciderTests(SimpleTestCase):
    def test_region_lead_decides_any_region(self):
        from api.views.short_card import _can_decide_sprout
        ctx = {'position_code': 'region_lead', 'region_code': '1', 'district_code': '1', 'group_districts': []}
        self.assertTrue(_can_decide_sprout(ctx, '6', '3'))
        team_lead = {**ctx, 'position_code': 'team_lead'}
        self.assertFalse(_can_decide_sprout(team_lead, '6', '3'))
        self.assertTrue(_can_decide_sprout(team_lead, '1', '3'))
        self.assertTrue(_can_decide_sprout({**ctx, 'position_code': 'region_general_secretary'}, '6', '3'))
        for code in ('region_clerk', 'region_mission_clerk'):
            self.assertFalse(_can_decide_sprout({**ctx, 'position_code': code}, '1', '1'))


class SproutBoardTests(SimpleTestCase):
    def test_rich_blocks_counts_districts_and_roster(self):
        from api.telegram import sprout_board as b
        full = {f: 'x' for f in ['age', 'gender', 'phone', 'residence', 'school_major', 'environment', 'relation',
                                 'personality', 'hobby', 'has_partner', 'family_relation', 'desired_image',
                                 'recent_concern', 'family_atmosphere', 'human_relations']}
        groups = [{'region_code': '1', 'group_name': '1반', 'district_codes': '1,2'},
                  {'region_code': '1', 'group_name': '2반', 'district_codes': '3'}]
        cards = [{**full, 'region_code': '1', 'district_code': '1', 'name': '<지인>', 'author_name': '인도자', 'sprout_status': 'approved'},
                 {**full, 'region_code': '1', 'district_code': '3', 'name': 'b', 'author_name': 'c', 'sprout_status': 'pending'}]
        districts = [{'region_code': '1', 'district_code': d} for d in ('1', '2', '3')]
        with patch.object(b, '_fetch', return_value=(groups, cards, districts)):
            blocks = b.build_blocks(None)
        main = blocks[4]['blocks'][0]['cells']
        texts = lambda row: [c['text']['text'] if isinstance(c['text'], dict) else c['text'] for c in row]
        self.assertEqual(texts(main[0]), ['지역', '1반', '2반', '합계', '대기'])
        self.assertEqual(texts(main[1]), ['1지역', '1/5', '0/5', '1/10', '1'])
        self.assertEqual(texts(blocks[2]['blocks'][0]['cells'][1]), ['1지역', '1', '0', '0', '1'])
        roster = blocks[3]['blocks'][0]['blocks'][0]['cells']
        self.assertEqual(texts(roster[1]), ['1구역', '<지인>', '인도자'])
