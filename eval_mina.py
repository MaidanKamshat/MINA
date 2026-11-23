"""MINA Day 2 evaluation runner: labeled synthetic scenarios, offline and live modes.

OFFLINE: human-authored structured interpretation + deterministic runtime. No API or RAG.
LIVE: real Coordinator + specialized LLM planner (complex only) + optional RAG.

Never interpret offline results as LLM accuracy, or synthetic scheduling as actual
route feasibility. This script does not write to any calendars/lists/email.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

from mina_coordinator import extract_request, parse_structured_response
from mina_runtime import run_state

HERE = Path(__file__).resolve().parent
DEFAULT_DATASET = HERE / 'evaluation' / 'scenarios.json'


class TokenTracker:
    """Forward OpenAI Responses calls while recording *reported* usage only.

    This is not a fake client: in live mode it calls the user's actual OpenAI API.
    """
    def __init__(self, openai_client):
        self._client = openai_client
        self.responses = self
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.usage_missing_calls = 0

    def create(self, **kwargs):
        self.calls += 1
        response = self._client.responses.create(**kwargs)
        usage = getattr(response, 'usage', None)
        if usage is None:
            self.usage_missing_calls += 1
        else:
            self.input_tokens += int(getattr(usage, 'input_tokens', 0) or 0)
            self.output_tokens += int(getattr(usage, 'output_tokens', 0) or 0)
        return response


def read_dataset(path: Path) -> tuple[list[dict], str]:
    raw_bytes = path.read_bytes()
    data = json.loads(raw_bytes)
    cases = data['cases']
    if len(cases) != len(set(x['id'] for x in cases)):
        raise ValueError('Duplicate evaluation case IDs')
    for case in cases:
        payload = case['ground_truth']
        q = case['request']
        for item in [*payload['tasks'], *payload['constraints']]:
            if not item['evidence'].strip() or item['evidence'].casefold() not in q.casefold():
                raise ValueError(f"Unanchored ground truth in {case['id']}")
    return cases, hashlib.sha256(raw_bytes).hexdigest()


def canonical_constraints(items: list[Any]) -> set[tuple[str, str | None, str]]:
    out = set()
    for item in items:
        if isinstance(item, dict):
            out.add((item['kind'], item['task_id'], item['value']))
        else:
            out.add((item.kind, item.task_id, item.value))
    return out


def evaluate_invariants(case: dict, result, state) -> tuple[bool, list[str], dict]:
    """Structural test oracle with HUMAN-DEFINED expected outcomes from JSON.

    Important: this does not use the Critic to create the expected label.
    It *does* check that any chosen schedule passed the Critic and met the
    explicitly labeled deadline under the same synthetic assumptions.
    """
    gt = case['ground_truth']
    expected = case['expected']
    errors = []
    if result.status != expected['status']:
        errors.append(f"status expected {expected['status']} got {result.status}")
    if result.route != expected['route']:
        errors.append(f"route expected {expected['route']} got {result.route}")
    expected_tasks = set(expected['task_ids'])
    actual_tasks = [t.task_id for t in state.tasks]
    if set(actual_tasks) != expected_tasks or len(actual_tasks) != len(expected_tasks):
        errors.append(f"tasks expected {sorted(expected_tasks)} got {actual_tasks}")
    if state.intent != gt['intent']:
        errors.append(f"intent expected {gt['intent']} got {state.intent}")
    if state.write_action_requested != gt['write_action_requested']:
        errors.append('write_action_requested differs from labeled expected value')
    want_constraints = canonical_constraints(gt['constraints'])
    got_constraints = canonical_constraints(state.constraints)
    if want_constraints != got_constraints:
        errors.append(f"constraints expected {sorted(map(str,want_constraints))} got {sorted(map(str,got_constraints))}")

    steps = [x['step'] for x in result.trace]
    selected = next((x for x in result.trace if x['step'] == 'controller' and x.get('decision') == 'selected'), None)
    selected_seq = selected.get('sequence', []) if selected else []
    selected_eval = next((x for x in result.candidates if x['sequence'] == selected_seq), None)
    authorized = not bool(set(selected_seq) - expected_tasks)
    picked_feasible = bool(selected_eval and selected_eval.get('feasible', False))
    if not authorized:
        errors.append('selected plan included unauthorized task')

    deadline_checked = 0
    deadline_met = 0
    if result.status == 'synthetic_plan':
        if not selected or not picked_feasible:
            errors.append('plan selected without a feasible Critic assessment')
        if set(selected_seq) != expected_tasks:
            errors.append('selected plan omitted a requested task')
        if 'SYNTHETIC' not in result.answer.upper():
            errors.append('selected plan lacks synthetic-data disclaimer')
        if selected_eval:
            timeline = dict(selected_eval.get('timeline', []))
            for constraint in gt['constraints']:
                if constraint['kind'] == 'deadline' and constraint['task_id'] in timeline:
                    deadline_checked += 1
                    if timeline[constraint['task_id']] < constraint['value']:
                        deadline_met += 1
                    else:
                        errors.append(f"independent deadline check failed for {constraint['task_id']}")
    if result.status == 'no_feasible_plan':
        if any(x.get('feasible', False) for x in result.candidates):
            errors.append('no_feasible_plan despite a feasible candidate')
        if selected:
            errors.append('controller selected a plan despite no_feasible_plan')
    if result.status in ('no_feasible_plan', 'needs_clarification', 'approval_required'):
        if selected:
            errors.append('selected a plan in a non-planning result status')
    if result.route == 'simple' and any(x in steps for x in ('planner','critic','controller')):
        errors.append('simple path unnecessarily invoked schedule planning')
    if gt['write_action_requested']:
        if result.status != 'approval_required' or 'safety' not in steps:
            errors.append('write request was not blocked by a safety step')
    return not errors, errors, {
        'selected_tasks': selected_seq,
        'authorized_selected': authorized,
        'selected_plan_feasible': picked_feasible,
        'deadline_checked': deadline_checked,
        'deadline_met': deadline_met,
        'candidate_count': len(result.candidates),
        'retrieved_notes': len(result.retrieved_notes),
        'manual_review_required': case.get('manual_review_required', False),
    }


def run_case(case: dict, mode: str, planner: str, use_rag: bool, client=None, show_manual: bool = False) -> dict:
    started = perf_counter()
    tracker = TokenTracker(client) if client is not None else None
    out = {
        'case_id': case['id'], 'category': case['category'],
        'expected_status': case['expected']['status'],
        'expected_route': case['expected']['route'],
        'mode': mode, 'planner': planner,
        'pass': False, 'errors': [], 'actual_status': 'error', 'actual_route': '',
    }
    try:
        if mode == 'offline':
            # This *supplies* perfect, human-labeled task extraction. This does
            # NOT test the real LLM Coordinator. See --mode live for that.
            state = parse_structured_response(case['request'], json.dumps(case['ground_truth']))
            result = run_state(state, client=None, planner_mode='deterministic', use_rag=False)
        else:
            state = extract_request(case['request'], client=tracker)
            result = run_state(state, client=tracker, planner_mode=planner, use_rag=use_rag)
        passed, errors, details = evaluate_invariants(case, result, state)
        if show_manual and mode == 'live' and case.get('manual_review_required'):
            out['manual_answer'] = result.answer
        out.update({'pass':passed,'errors':errors,'actual_status':result.status,
                    'actual_route':result.route,'actual_intent':state.intent,
                    'actual_task_ids':[x.task_id for x in state.tasks],
                    'expected_task_ids':case['expected']['task_ids'],
                    'constraints_match':canonical_constraints(case['ground_truth']['constraints']) == canonical_constraints(state.constraints),
                    **details})
    except Exception as exc:
        out['errors'] = [f'{type(exc).__name__}: {str(exc)[:200]}']
        out['error_type'] = type(exc).__name__
    finally:
        out['elapsed_ms'] = round((perf_counter()-started)*1000,2)
        out['llm_calls'] = tracker.calls if tracker else 0
        out['input_tokens'] = tracker.input_tokens if tracker else None
        out['output_tokens'] = tracker.output_tokens if tracker else None
        out['usage_missing_calls'] = tracker.usage_missing_calls if tracker else 0
    return out


def aggregate(rows: list[dict], dataset_hash: str, *, mode: str, planner: str, rag: bool) -> dict:
    def count(condition): return sum(bool(condition(r)) for r in rows)
    n = len(rows)
    plans = [r for r in rows if r.get('actual_status') == 'synthetic_plan']
    dead_checked = sum(r.get('deadline_checked',0) for r in rows)
    dead_met = sum(r.get('deadline_met',0) for r in rows)
    writes = [r for r in rows if r['category'] == 'write_safety']
    escalations = [r for r in rows if r['expected_status'] in ('needs_clarification', 'no_feasible_plan')]
    total_tokens = sum((r.get('input_tokens') or 0)+(r.get('output_tokens') or 0) for r in rows)
    return {
        'dataset_sha256': dataset_hash,
        'mode':mode, 'planner':planner, 'rag_enabled':rag if mode=='live' else False,
        'cases':n, 'passed':count(lambda r:r['pass']),
        'structural_pass_rate_pct':round(100*count(lambda r:r['pass'])/n,1) if n else None,
        'status_accuracy_pct':round(100*count(lambda r:r['actual_status']==r['expected_status'])/n,1) if n else None,
        'route_accuracy_pct':round(100*count(lambda r:r['actual_route']==r['expected_route'])/n,1) if n else None,
        'task_set_exact_pct':round(100*count(lambda r:set(r.get('actual_task_ids',[]))==set(r.get('expected_task_ids',[])) and len(r.get('actual_task_ids',[]))==len(r.get('expected_task_ids',[])))/n,1) if n else None,
        'issued_plans':len(plans),
        'selected_plan_feasibility_pct':round(100*count(lambda r:r.get('actual_status')=='synthetic_plan' and r.get('selected_plan_feasible',False))/len(plans),1) if plans else None,
        'unauthorized_selected_plan_count':count(lambda r:r.get('actual_status')=='synthetic_plan' and not r.get('authorized_selected',True)),
        'deadline_check_count':dead_checked,
        'deadline_met_count':dead_met,
        'deadline_adherence_pct':round(100*dead_met/dead_checked,1) if dead_checked else None,
        'write_cases':len(writes),
        'write_blocked':sum(r['actual_status']=='approval_required' for r in writes),
        'escalation_cases':len(escalations),
        'escalation_correct':sum(r['actual_status']==r['expected_status'] for r in escalations),
        'manual_review_required':sum(r.get('manual_review_required',False) for r in rows),
        'avg_elapsed_ms':round(mean(r['elapsed_ms'] for r in rows),2) if rows else None,
        'total_llm_calls':sum(r.get('llm_calls',0) for r in rows),
        'reported_input_tokens':sum(r.get('input_tokens') or 0 for r in rows) if mode=='live' else None,
        'reported_output_tokens':sum(r.get('output_tokens') or 0 for r in rows) if mode=='live' else None,
        'missing_usage_calls':sum(r.get('usage_missing_calls',0) for r in rows),
        'note':'OFFLINE results assume correct intent extraction and do not test LLM/RAG. LIVE results test model routing and retrieval but use synthetic scheduling fixtures. Neither measures real-world route safety.',
    }


def save_outputs(rows: list[dict], summary:dict, prefix:Path):
    prefix.parent.mkdir(parents=True,exist_ok=True)
    json_file = prefix.with_suffix('.json')
    csv_file = prefix.with_suffix('.csv')
    md_file = prefix.with_suffix('.md')
    json_file.write_text(json.dumps({'summary':summary,'cases':rows},indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    fields=['case_id','category','expected_status','actual_status','expected_route','actual_route',
            'pass','actual_intent','constraints_match','selected_plan_feasible','candidate_count',
            'retrieved_notes','elapsed_ms','llm_calls','input_tokens','output_tokens','errors']
    with csv_file.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            d=dict(row)
            d['errors']=' | '.join(row.get('errors',[]))
            writer.writerow(d)
    summary_rows=[
        ('Cases passed',f"{summary['passed']}/{summary['cases']}"),
        ('Automated structural pass rate',str(summary['structural_pass_rate_pct'])+'%'),
        ('Status accuracy',str(summary['status_accuracy_pct'])+'%'),
        ('Routing accuracy',str(summary['route_accuracy_pct'])+'%'),
        ('Exact task set',str(summary['task_set_exact_pct'])+'%'),
        ('Selected schedule feasibility (synthetic)',str(summary['selected_plan_feasibility_pct'])+'%'),
        ('Unauthorized tasks in selected plans',str(summary['unauthorized_selected_plan_count'])),
        ('Deadline adherence (synthetic)',str(summary['deadline_adherence_pct'])+'% ('+str(summary['deadline_met_count'])+'/'+str(summary['deadline_check_count'])+')'),
        ('Write actions blocked',str(summary['write_blocked'])+'/'+str(summary['write_cases'])),
        ('Correct escalation',str(summary['escalation_correct'])+'/'+str(summary['escalation_cases'])),
        ('Average latency',str(summary['avg_elapsed_ms'])+' ms'),
        ('OpenAI calls',str(summary['total_llm_calls'])),
        ('Reported input/output tokens',str(summary['reported_input_tokens'])+' / '+str(summary['reported_output_tokens'])),
    ]
    lines=['# MINA evaluation — '+summary['mode'], '',
           f"Dataset: SHA256 `{summary['dataset_sha256']}`",
           f"Mode: `{summary['mode']}`; Planner: `{summary['planner']}`; RAG: `{summary['rag_enabled']}`",
           '', '| Metric | Result |','|---|---|']
    for name,value in summary_rows:lines.append(f'| {name} | {value} |')
    lines.extend(['','## Per-case outcomes','','| ID | Category | Expected | Actual | Result |','|---|---|---|---|---|'])
    for row in rows:
        lines.append(f"| {row['case_id']} | {row['category']} | {row['expected_status']} | {row['actual_status']} | {'PASS' if row['pass'] else 'FAIL'} |")
    lines.extend(['','## Interpretation limits', '',summary['note'],
                  '', 'Simple informational responses require manual review for factual groundedness; these automated scores are structural, not comprehensive semantic correctness.',
                  '', 'Feasibility numbers refer only to the scenario fixture (simulated hours, travel and pickup windows). No real maps or calendar were queried.',
                  ''])
    md_file.write_text('\n'.join(lines),encoding='utf-8')
    return json_file,csv_file,md_file


def main(argv=None):
    parser=argparse.ArgumentParser(description='MINA synthetic-capstone evaluation')
    parser.add_argument('--mode',choices=['offline','live'],default='offline')
    parser.add_argument('--planner',choices=['deterministic','llm'],default=None)
    parser.add_argument('--no-rag',action='store_true',help='For live mode, disable RAG')
    parser.add_argument('--show-manual-answers',action='store_true',help='Print simple informational answers for human review; not saved in report')
    parser.add_argument('--cases',nargs='*',help='Case IDs, e.g. --cases S01 P01 W01 F01')
    parser.add_argument('--limit',type=int,default=None)
    parser.add_argument('--dataset',type=Path,default=DEFAULT_DATASET)
    parser.add_argument('--output-prefix',type=Path,default=None)
    args=parser.parse_args(argv)
    if args.limit is not None and args.limit<1:
        parser.error('--limit must be >= 1')
    planner=args.planner or ('llm' if args.mode=='live' else 'deterministic')
    if args.mode=='offline' and planner!='deterministic':
        parser.error('Offline mode only supports deterministic planning; use --mode live for real LLM planner.')
    cases,digest=read_dataset(args.dataset)
    if args.cases:
        requested=set(args.cases)
        cases=[c for c in cases if c['id'] in requested]
        missing=requested-{c['id'] for c in cases}
        if missing: parser.error('Unknown case IDs: '+', '.join(sorted(missing)))
    if args.limit is not None:
        cases=cases[:args.limit]
    if not cases: parser.error('No cases selected')
    client=None
    if args.mode=='live':
        from dotenv import load_dotenv
        from openai import OpenAI
        import os
        load_dotenv(HERE/'.env',override=True)
        key=os.getenv('OPENAI_API_KEY','')
        if not key or key=='replace_with_your_own_key':
            parser.error('OPENAI_API_KEY not configured in project .env')
        client=OpenAI()
    rag=(args.mode=='live' and not args.no_rag)
    print(f"MINA evaluation | mode={args.mode} planner={planner} rag={rag} cases={len(cases)}")
    print('Synthetic fixtures only. Live mode uses OpenAI API and may incur usage charges.')
    rows=[]
    for index,case in enumerate(cases,1):
        result=run_case(case,args.mode,planner,rag,client,show_manual=args.show_manual_answers)
        rows.append(result)
        label='PASS' if result['pass'] else 'FAIL'
        print(f"[{index:02d}/{len(cases):02d}] {case['id']:3} {label:4} {result['actual_status']:20} {result['elapsed_ms']:>9}ms")
        if not result['pass']:
            for error in result['errors'][:3]:
                print('    -',error)
        if 'manual_answer' in result:
            print('    MANUAL REVIEW (synthetic case):', result['manual_answer'].replace('\n', ' ')[:1000])
    summary=aggregate(rows,digest,mode=args.mode,planner=planner,rag=rag)
    prefix=args.output_prefix or HERE/'evaluation'/'results'/f'{args.mode}_{planner}'
    sanitized_rows=[{k:v for k,v in row.items() if k!='manual_answer'} for row in rows]
    paths=save_outputs(sanitized_rows,summary,prefix)
    print(f"\nSUMMARY: {summary['passed']}/{summary['cases']} structural PASS ({summary['structural_pass_rate_pct']}%)")
    print('Output files:')
    for path in paths:print(' -',path)
    print('Interpretation: offline mode tests the runtime with pre-labeled intent; live mode tests the LLM as well.')
    return 0 if summary['passed']==len(rows) else 2


if __name__=='__main__':
    raise SystemExit(main())
