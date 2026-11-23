"""Optional, privacy-minimizing JSONL audit records for MINA's synthetic MVP.

No prompts, responses, secrets, retrieved note contents, or exception messages
are written. The resulting log is suitable for reproducible synthetic evaluation,
not a full production security audit.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

# Explicit allowlist: fallback exception details may contain user text.
SAFE_TRACE_KEYS = frozenset({
    'step', 'route', 'intent', 'task_ids', 'note_ids', 'source', 'start',
    'deadlines', 'library_open', 'durations', 'method', 'count',
    'passed', 'evaluated', 'decision', 'sequence', 'score',
    'status', 'error_type', 'reason_type',
})


def audit_record(result, *, mode: str, rag_enabled: bool, elapsed_ms: float) -> dict:
    """Only whitelisted operational metadata; no raw user input/output."""
    checks = [
        {
            'sequence': item.get('sequence', []),
            'feasible': bool(item.get('feasible', False)),
            'score': item.get('score'),
        }
        for item in result.candidates
    ]
    return {
        'run_id': uuid4().hex,
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'status': result.status,
        'route': result.route,
        'planner_mode': mode,
        'rag_enabled': bool(rag_enabled),
        'elapsed_ms': round(elapsed_ms, 2),
        'retrieved_note_ids': [n.get('id') for n in result.retrieved_notes],
        'candidate_checks': checks,
        'trace': [{k: event[k] for k in SAFE_TRACE_KEYS if k in event}
                  for event in result.trace],
    }


def append_audit_log(path: str | Path, record: dict) -> Path:
    """Append one JSON object per line to a local evaluation file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + '\n')
    return path
