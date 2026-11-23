"""Offline audit tests, no API calls."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mina_audit import audit_record, append_audit_log
from mina_runtime import RuntimeResult, run_state
from mina_state import RequestState


class AuditTests(unittest.TestCase):
    def test_does_not_log_prompt_or_answer_or_fallback_reason(self):
        result = RuntimeResult(
            status='needs_clarification', route='complex',
            answer='SECRET USER RESPONSE',
            trace=[{'step': 'fallback', 'reason': 'SECRET USER REQUEST',
                    'reason_type': 'ValueError'}],
        )
        record = audit_record(result, mode='llm', rag_enabled=True, elapsed_ms=12.345)
        contents = json.dumps(record)
        self.assertNotIn('SECRET', contents)
        self.assertEqual(record['elapsed_ms'], 12.35)
        self.assertEqual(record['trace'][0]['step'], 'fallback')
        self.assertEqual(record['trace'][0]['reason_type'], 'ValueError')

    def test_append_jsonl_and_read_back(self):
        result = RuntimeResult('approval_required', 'simple', 'nothing modified',
                               trace=[{'step': 'safety', 'decision': 'no write tools; no modification'}])
        record = audit_record(result, mode='deterministic', rag_enabled=False, elapsed_ms=1)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'evaluation' / 'runs.jsonl'
            append_audit_log(path, record)
            append_audit_log(path, record)
            rows = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['status'], 'approval_required')
        self.assertFalse(rows[0]['rag_enabled'])
        self.assertNotIn('nothing modified', json.dumps(rows))

    def test_simple_trace_has_no_planning(self):
        state = RequestState('What to pack for school?', 'information', route='simple')
        result = run_state(state, planner_mode='deterministic', use_rag=False)
        record = audit_record(result, mode='deterministic', rag_enabled=False, elapsed_ms=2)
        self.assertEqual(record['route'], 'simple')
        self.assertNotIn('planner', [s['step'] for s in record['trace']])


if __name__ == '__main__':
    unittest.main(verbosity=2)
