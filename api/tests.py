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

    def test_stage2_plus_approval_is_sprout(self):
        from api.views.short_card import _journal_stage
        self.assertEqual(_journal_stage({**self.FULL, 'sprout_status': None}), '새싹')
        self.assertEqual(_journal_stage({**self.FULL, 'sprout_status': 'pending'}), '새싹')
        self.assertEqual(_journal_stage({**self.FULL, 'sprout_status': 'approved'}), '떡잎')
        # 3단계는 비어도 2단계까지 채우고 재가되면 떡잎(2026-10-05)
        no3 = {**self.FULL, 'desired_image': None, 'recent_concern': None, 'family_atmosphere': None, 'human_relations': None}
        self.assertEqual(_journal_stage({**no3, 'sprout_status': 'approved'}), '떡잎')
        self.assertEqual(_journal_stage({**self.FULL, 'hobby': None, 'sprout_status': 'approved'}), '씨앗')

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
        self.assertEqual(texts(main[0]), ['지역', '반', '반', '합계', '대기'])
        self.assertEqual(texts(main[1]), ['1지역', '1반 1/5', '2반 0/5', '1/10', '1'])
        self.assertEqual(texts(blocks[2]['blocks'][0]['cells'][1]), ['1지역', '1', '0', '0', '1'])
        roster = blocks[3]['blocks'][0]['blocks'][0]['cells']
        self.assertEqual(texts(roster[1]), ['1구역', '<지인>', '인도자'])


class RegionShedBoardTests(SimpleTestCase):
    def test_region_group_resolves_to_single_region(self):
        from api.telegram import shed_union_dashboards as u
        self.assertEqual(u._union_regions(None, '3'), ['3'])
        self.assertEqual(u._team_id_for_group('3'), '3')
        self.assertEqual(u._team_id_for_group('135'), '135 연합')
        self.assertEqual(u._group_label('3'), '3지역')
        self.assertEqual(u._group_label('246'), '질적찾기')

    def test_region_timetable_uses_135_style(self):
        from api.telegram.shed_union_dashboards import _sched_person
        r = {'caller_name': None, 'introducer_name': '유입', 'sender_name': '선문자'}
        self.assertEqual(_sched_person('4', r), '선문자')
        self.assertEqual(_sched_person('246', r), '유입')


@override_settings(TG_CALLBACK_HMAC_SECRET='s')
class TelegramMatchResultTests(SimpleTestCase):
    ROW = {'sarang_id': 'A' * 24 + '36017851', 'name': '홍길동', 'mt': '10/08 19:00'}

    def _run(self, code):
        from api.telegram import match_result_input as m
        sent = []
        with patch.object(m, '_find_open', return_value=self.ROW), \
             patch.object(m.tel_router_client, 'enqueue', side_effect=lambda meth, p, **k: sent.append((meth, p))), \
             patch('api.views.assets.record_match_result', return_value=True) as rmr, \
             patch('api.views.assets.record_postpone', return_value=True) as rp:
            toast = m.handle_callback(None, f'36017851.{code}', -100123, 7, lambda c, sid: 'actor')
        return toast, sent, rmr, rp

    def test_parse_date(self):
        import datetime
        from api.telegram.match_result_input import parse_date
        today = datetime.date(2026, 10, 8)
        self.assertEqual(parse_date('10/12 19:00', today), '2026-10-12 19:00')
        self.assertEqual(parse_date('10.12 7시', today), '2026-10-12 07:00')
        self.assertEqual(parse_date('1/3 19:30', today), '2027-01-03 19:30')
        self.assertIsNone(parse_date('내일 저녁', today))

    def test_callback_data_fits_telegram_limit(self):
        from api.telegram.match_result_input import _cb
        self.assertLessEqual(len(_cb(-1001234567890, '36017851', 'U4').encode()), 64)

    def test_sub_reason_records_result(self):
        _, sent, rmr, _ = self._run('U2')
        rmr.assert_called_once_with(None, self.ROW['sarang_id'], 'UNFIT', 'PERSONALITY_UNFIT')
        self.assertIn('인성비합 입력 완료', sent[-1][1]['text'])

    def test_consult_win_and_undecided_postpone(self):
        _, _, rmr, _ = self._run('W')
        rmr.assert_called_once_with(None, self.ROW['sarang_id'], 'CONSULT_WIN', None)
        _, _, _, rp = self._run('S0')
        rp.assert_called_once_with(None, self.ROW['sarang_id'], '2차만남', '미정', 'actor')

    def test_postpone_prompt_carries_tag(self):
        _, sent, rmr, rp = self._run('D')
        self.assertIn('#r_36017851D', sent[-1][1]['text'])
        rmr.assert_not_called(); rp.assert_not_called()


class TelegramNameCommandTests(SimpleTestCase):
    def _post(self, body, found):
        from api.views import internal_telegram as it
        with patch.object(it, 'check_internal_auth', return_value=True), \
             patch.object(it, 'DataRouterClient'), \
             patch.object(it, 'find_open_matches', return_value=found), \
             patch.object(it, '_assign_teacher', return_value={'ok': True, 'message': 'done'}) as assign:
            r = self.client.post('/internal/telegram/teacher-assign', data=json.dumps(body), content_type='application/json')
        return json.loads(r.content), assign

    def test_teacher_by_name(self):
        one = [{'sarang_id': 'x', 'short': 'AB12CD34', 'name': '홍길동', 'mt': '10/08 19:00', 'guide': '나유진'}]
        res, assign = self._post({'name': '홍길동', 'teacherName': '김철수', 'chatId': -1}, one)
        assign.assert_called_once()
        self.assertEqual(assign.call_args[0][1:], ('AB12CD34', '김철수'))
        two = one + [{**one[0], 'short': 'FF00FF00', 'mt': '10/09 18:00'}]
        res, assign = self._post({'name': '홍길동', 'teacherName': '김철수', 'chatId': -1}, two)
        assign.assert_not_called()
        self.assertIn('2명', res['message'])
        self.assertIn('/t_ff00ff00 김철수', res['message'])
        res, _ = self._post({'name': '없음', 'teacherName': '김철수', 'chatId': -1}, [])
        self.assertIn('못 찾았어', res['message'])


class JournalEditPermissionTests(SimpleTestCase):
    def test_author_or_district_lead(self):
        from api.views.short_card import _can_edit_journal
        client = MagicMock()
        self.assertTrue(_can_edit_journal(client, 'A', 'A'))
        client.query_one.assert_not_called()
        client.query_one.return_value = {'ok': '1'}
        self.assertTrue(_can_edit_journal(client, 'LEAD', 'A'))
        self.assertEqual(client.query_one.call_args[0][1], ['A', 'LEAD'])
        client.query_one.return_value = None
        self.assertFalse(_can_edit_journal(client, 'OTHER', 'A'))


class ShedGachaRegionTests(SimpleTestCase):
    def _run(self, region, rnd):
        from api.views import assets
        f = assets.run_shed_gacha
        while hasattr(f, '__wrapped__'):
            f = f.__wrapped__
        client = MagicMock()
        client.query_one.return_value = {'introducer_member_id': 'INFLOW', 'region_code': region, **getattr(self, 'extra', {})}
        client.exec.return_value = 1
        req = MagicMock(method='POST', body=json.dumps({'docId': 'S', 'inflowName': '유입', 'tmName': '티엠'}).encode())
        with patch.object(assets, 'DataRouterClient', return_value=client), \
             patch.object(assets, '_member_id_by_name', return_value='TM'), \
             patch.object(assets, 'send_habjaeyang_to_telegram'), \
             patch.object(assets.random, 'random', return_value=rnd) as roll:
            res = json.loads(f(req).content)
        return res, client.exec.call_args[0][1][0], roll

    def test_roulette_only_in_regions_1_and_5(self):
        res, guide, roll = self._run('1', 0.3)
        self.assertEqual((res['roulette'], res['winner'], guide), (True, 'tm', 'TM'))
        res, guide, _ = self._run('5', 0.9)
        self.assertEqual((res['winner'], guide), ('inflow', 'INFLOW'))
        res, guide, roll = self._run('3', 0.0)
        self.assertEqual((res['roulette'], res['winner'], guide), (False, 'inflow', 'INFLOW'))
        roll.assert_not_called()


class ShedGachaPublicTests(ShedGachaRegionTests):
    def test_roulette_only_in_regions_1_and_5(self):
        pass  # 부모 케이스는 공개 아님 — 여기선 공개 건만

    def test_public_item_always_goes_to_tm(self):
        import datetime
        from django.utils import timezone
        today = timezone.localdate()
        old = (today - datetime.timedelta(days=5)).isoformat()
        self.extra = {'received_day': '2026-10-08', 'inflow_day': old, 'calls': '0'}
        res, guide, roll = self._run('3', 0.99)  # 룰렛 없는 지역이어도
        self.assertEqual((res['public'], res['winner'], guide), (True, 'tm', 'TM'))
        res, guide, roll = self._run('1', 0.99)  # 룰렛 지역이어도 룰렛 안 돌림
        self.assertEqual((res['roulette'], res['winner']), (False, 'tm'))
        roll.assert_not_called()
        self.extra = {'received_day': '2026-10-08', 'inflow_day': today.isoformat(), 'calls': '4'}
        res, _, _ = self._run('3', 0.0)
        self.assertEqual(res['winner'], 'tm')
        self.extra = {'received_day': '2026-10-01', 'inflow_day': old, 'calls': '9'}  # 합당한자 이전 건은 해당 없음
        res, guide, _ = self._run('3', 0.0)
        self.assertEqual((res['public'], guide), (False, 'INFLOW'))
