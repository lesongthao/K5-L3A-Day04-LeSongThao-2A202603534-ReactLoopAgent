"""Kiem tra hanh vi dieu tra bang tool/AI gia lap, khong goi API."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent import _missing_evidence, run_agent
from bonus.tools import BonusTools, SCHEMAS as BONUS_SCHEMAS
from status_tools import SCHEMAS
from test_lab import FakeProvider, tool_call, final


class EvidenceTools:
    schemas = SCHEMAS

    def execute(self, name, args):
        if name == 'get_status':
            return {'provider': args['provider'], 'source': 'https://www.githubstatus.com', 'incidents': []}
        incident_id = args['incident_id']
        body = 'Status update.'
        if incident_id == 'initial':
            body = 'Related report: https://www.githubstatus.com/incidents/followup'
        return {
            'ok': True, 'provider': args['provider'], 'id': incident_id,
            'url': 'https://www.githubstatus.com/incidents/' + incident_id,
            'updates': [{'body': body, 'truncated': incident_id == 'shortened'}],
            'updates_total': 1
        }


class InvestigationTests(unittest.TestCase):
    def test_scope_comparison_does_not_require_all_candidates_or_pages(self):
        trace = [
            {'event': 'tool', 'name': 'get_vercel_status', 'arguments': {}, 'result': {
                'provider': 'vercel', 'incidents': [{'id': 'chosen'}, {'id': 'other'}]}},
            {'event': 'tool', 'name': 'get_incident_details',
             'arguments': {'provider': 'vercel', 'incident_id': 'chosen'}, 'result': {
                 'ok': True, 'provider': 'vercel', 'id': 'chosen', 'next_offset': 3,
                 'updates': [{'body': 'Build impact. https://www.githubstatus.com/incidents/related'}]}}
        ]
        pending = _missing_evidence('Doi chieu pham vi Vercel.', trace, BONUS_SCHEMAS,
                                    'Chi doc mot phan bao cao; con trang chua doc.')
        self.assertEqual(pending, [])
        timeline = _missing_evidence('Tra timeline Vercel.', trace, BONUS_SCHEMAS, '', check_answer=False)
        self.assertTrue(any('Con trang timeline' in item for item in timeline))

    def test_unrelated_component_requires_broad_lookup_before_incident_choice(self):
        trace = [{'event': 'tool', 'name': 'get_npm_status',
                  'arguments': {'component': 'Registry'},
                  'result': {'provider': 'npm', 'incidents': [{'id': 'registry-report'}]}}]
        pending = _missing_evidence('Doi chieu pham vi npm publishing.', trace, BONUS_SCHEMAS, '', check_answer=False)
        self.assertTrue(any('status khong loc' in item for item in pending))
        self.assertFalse(any('registry-report' in item for item in pending))
        trace.append({'event': 'tool', 'name': 'get_npm_status', 'arguments': {},
                      'result': {'provider': 'npm', 'incidents': [{'id': 'publishing-report'}]}})
        pending = _missing_evidence('Doi chieu pham vi npm publishing.', trace, BONUS_SCHEMAS, '', check_answer=False)
        self.assertTrue(any('publishing-report' in item for item in pending))
        self.assertFalse(any('status khong loc' in item for item in pending))

    def test_comparison_requires_each_observed_snapshot_time(self):
        trace = [
            {'event': 'tool', 'name': 'get_vercel_status', 'arguments': {},
             'result': {'provider': 'vercel', 'captured_at': '2026-11-10T01:02:03+00:00'}},
            {'event': 'tool', 'name': 'get_npm_status', 'arguments': {},
             'result': {'provider': 'npm', 'captured_at': '2026-11-10T04:05:06+00:00'}}
        ]
        question = 'So sanh Vercel va npm.'
        answer = 'Vercel: 2026-11-10T01:02:03+00:00.'
        pending = _missing_evidence(question, trace, BONUS_SCHEMAS, answer)
        self.assertEqual(len(pending), 1)
        self.assertIn('snapshot cua npm', pending[0])
        self.assertEqual(_missing_evidence(question, trace, BONUS_SCHEMAS,
                         answer + ' npm: 2026-11-10T04:05:06+00:00.'), [])

    def test_scope_comparison_reads_incident_details(self):
        class ScopeTools(EvidenceTools):
            def execute(self, name, args):
                result = super().execute(name, args)
                if name == 'get_status':
                    result['incidents'] = [{'id': 'scope-report'}]
                return result

        url = 'https://www.githubstatus.com/incidents/scope-report'
        ai = FakeProvider([
            tool_call('1', 'get_status', '{"provider":"github"}'),
            final('Status summary. https://www.githubstatus.com'),
            tool_call('2', 'get_incident_details', '{"provider":"github","incident_id":"scope-report"}'),
            final('Scope from report. ' + url)
        ])
        result = run_agent('Doi chieu pham vi incident GitHub.', ai, ScopeTools())
        self.assertEqual(result['status'], 'completed')
        self.assertEqual([e['name'] for e in result['trace'] if e['event'] == 'tool'], ['get_status', 'get_incident_details'])
        self.assertIn('Chua doc chi tiet', ai.histories[1][0]['content'])

    def test_retryable_status_gets_another_attempt_before_final(self):
        tools = BonusTools(scenario='rate_limit_once')
        ai = FakeProvider([
            tool_call('1', 'get_vercel_status', '{"component":"Builds"}'),
            final('Chua kiem tra duoc Vercel.'),
            tool_call('2', 'get_vercel_status', '{}'),
            final('Vercel checked. https://www.vercel-status.com')
        ])
        result = run_agent('Kiem tra Vercel, retry co gioi han.', ai, tools)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(tools.calls[('get_vercel_status', 'vercel')], 2)
        self.assertIn('Con 1 lan thu lai', ai.histories[1][0]['content'])
        self.assertNotIn('Con 1 lan thu lai', ai.histories[-1][0]['content'])

    def test_user_can_decline_retry(self):
        ai = FakeProvider([
            tool_call('1', 'get_vercel_status', '{}'), final('Chua kiem tra duoc Vercel.')
        ])
        result = run_agent('Kiem tra Vercel, khong thu lai.', ai, BonusTools(scenario='rate_limit_once'))
        self.assertEqual(result['status'], 'completed')

    def test_current_status_requires_status_observation(self):
        url = 'https://www.githubstatus.com/incidents/historical'
        ai = FakeProvider([
            tool_call('1', 'get_incident_details', '{"provider":"github","incident_id":"historical"}'),
            final(url), tool_call('2', 'get_status', '{"provider":"github"}'), final(url)
        ])
        result = run_agent('GitHub status theo snapshot?', ai, EvidenceTools())
        self.assertEqual(result['status'], 'completed')
        self.assertTrue(any(e['event'] == 'validation_missing_evidence' for e in result['trace']))
        self.assertEqual([e['name'] for e in result['trace'] if e['event'] == 'tool'], ['get_incident_details', 'get_status'])

    def test_related_report_is_read_in_a_later_model_step(self):
        url = 'https://www.githubstatus.com/incidents/initial'
        ai = FakeProvider([
            tool_call('1', 'get_incident_details', '{"provider":"github","incident_id":"initial"}'),
            final(url), tool_call('2', 'get_incident_details', '{"provider":"github","incident_id":"followup"}'), final(url)
        ])
        result = run_agent('Dieu tra nguyen nhan GitHub.', ai, EvidenceTools())
        self.assertEqual(result['status'], 'completed')
        tools = [e for e in result['trace'] if e['event'] == 'tool']
        self.assertEqual([e['arguments']['incident_id'] for e in tools], ['initial', 'followup'])
        self.assertLess(tools[0]['step'], tools[1]['step'])

    def test_shortened_content_requires_limit_in_answer(self):
        url = 'https://www.githubstatus.com/incidents/shortened'
        ai = FakeProvider([
            tool_call('1', 'get_incident_details', '{"provider":"github","incident_id":"shortened"}'),
            final('Nguyen nhan. ' + url), final('Du lieu bi cat. ' + url)
        ])
        result = run_agent('Phan tich nguyen nhan GitHub.', ai, EvidenceTools())
        self.assertEqual(result['status'], 'completed')
        self.assertIn('bi cat', result['answer'])

    def test_pagination_is_completed_before_timeline_answer(self):
        class PagedTools:
            schemas = BONUS_SCHEMAS

            def execute(self, name, args):
                return {
                    'ok': True, 'provider': 'vercel', 'id': 'timeline',
                    'url': 'https://www.vercel-status.com/incidents/timeline',
                    'updates': [{'body': 'Update', 'truncated': False}],
                    'next_offset': 2 if args.get('offset', 0) == 0 else None
                }

        url = 'https://www.vercel-status.com/incidents/timeline'
        ai = FakeProvider([
            tool_call('1', 'get_incident_details', '{"provider":"vercel","incident_id":"timeline"}'),
            final(url), tool_call('2', 'get_incident_details', '{"provider":"vercel","incident_id":"timeline","offset":2}'), final(url)
        ])
        result = run_agent('Tra timeline Vercel.', ai, PagedTools())
        self.assertEqual(result['status'], 'completed')
        self.assertEqual([e['arguments'].get('offset', 0) for e in result['trace'] if e['event'] == 'tool'], [0, 2])

    def test_persistent_rate_limit_has_bounded_execution(self):
        tools = BonusTools(scenario='rate_limit_always')
        ai = FakeProvider([
            tool_call('1', 'get_vercel_status', '{}'),
            tool_call('2', 'get_vercel_status', '{}'),
            tool_call('3', 'get_vercel_status', '{}'), final('Chua kiem tra duoc Vercel.')
        ])
        result = run_agent('Kiem tra Vercel.', ai, tools)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(tools.calls[('get_vercel_status', 'vercel')], 2)
        observations = [e['result'] for e in result['trace'] if e['event'] == 'tool']
        self.assertEqual(observations[-1]['error'], 'RETRY_LIMIT_REACHED')

    def test_malformed_offset_is_observation_not_crash(self):
        ai = FakeProvider([
            tool_call('1', 'get_incident_details', '{"provider":"npm","incident_id":"unknown","offset":[]}'),
            final('Tham so khong hop le.')
        ])
        result = run_agent('Kiem tra.', ai, BonusTools())
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(json.loads(ai.histories[1][-1]['content'])['error'], 'INVALID_ARGUMENTS')

    def test_long_retry_after_does_not_trigger_immediate_request(self):
        class LimitedTools:
            schemas = BONUS_SCHEMAS

            def __init__(self):
                self.count = 0

            def execute(self, name, args):
                self.count += 1
                return {'ok': False, 'error': 'RATE_LIMITED', 'retry_after_seconds': 120}

        tools = LimitedTools()
        ai = FakeProvider([
            tool_call('1', 'get_vercel_status', '{}'), tool_call('2', 'get_vercel_status', '{}'), final('Chua kiem tra duoc.')
        ])
        with patch('agent.time.sleep') as sleep:
            result = run_agent('Kiem tra.', ai, tools)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(tools.count, 1)
        sleep.assert_not_called()


if __name__ == '__main__':
    unittest.main()
