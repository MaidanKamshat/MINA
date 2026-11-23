"""MINA Experiment 8: LLM candidate generation, deterministic evaluation.

No maps/calendar calls. Uses the existing OpenAI API key from .env.
The LLM proposes task orders; it cannot declare a plan feasible.
"""
import json
from pathlib import Path
from tot_planner import TASKS, FIXTURE, evaluate_candidate

MODEL = 'gpt-4.1-mini'
TEST_QUERY = ('Tomorrow I need to return library books, buy groceries, '
              'and pick up my daughter from school before 2:30 PM.')


def generate_llm_candidates(query, client=None):
    """Request three distinct candidate sequences as machine-readable JSON.

    Do not silently repair malformed output: show that as an experiment failure.
    """
    if client is None:
        from dotenv import load_dotenv
        from openai import OpenAI
        load_dotenv(Path(__file__).parent / '.env')
        client = OpenAI()
    response = client.responses.create(
        model=MODEL,
        instructions=(
            'You are the candidate generator in a controlled family-planning experiment. '
            'Generate exactly three DIFFERENT possible orderings of the three task IDs: '
            'library, groceries, school_pickup. '
            'Do not introduce other tasks or locations. Do not estimate times, travel, '
            'feasibility, or scores; a separate deterministic critic will do that. '
            'Return only JSON matching the schema.'
        ),
        input=(f'User request: {query}\n'
               'Task IDs: library = return books; groceries = buy groceries; '
               'school_pickup = pick up daughter. This is a synthetic test.'),
        text={'format': {
            'type': 'json_schema',
            'name': 'candidate_task_sequences',
            'strict': True,
            'schema': {
                'type': 'object',
                'properties': {
                    'candidates': {
                        'type': 'array',
                        'items': {
                            'type': 'array',
                            'items': {'type': 'string', 'enum': list(TASKS)},
                        },
                    }
                },
                'required': ['candidates'],
                'additionalProperties': False,
            },
        }},
    )
    data = json.loads(response.output_text)
    raw = data['candidates']
    if not isinstance(raw, list) or len(raw) != 3:
        raise ValueError('Generator must return exactly three candidates')
    sequences = []
    for index, item in enumerate(raw, 1):
        if not isinstance(item, list):
            raise ValueError(f'Candidate {index} must be an array')
        # Keep the original proposal. Critic, not the generator, rejects bad task sets.
        sequences.append(tuple(item))
    if len(set(sequences)) != len(sequences):
        raise ValueError('Generator returned duplicate candidates')
    return sequences


def assess_llm_candidates(candidates, fixture=FIXTURE):
    """Score only valid plans; never let LLM self-assess constraints."""
    checked = [(sequence, evaluate_candidate(sequence, fixture))
               for sequence in candidates]
    feasible = [(sequence, result) for sequence, result in checked
                if result['feasible']]
    best = max(feasible, key=lambda x: x[1]['score']) if feasible else None
    return checked, best


def display_time(clock_24):
    from datetime import datetime
    return datetime.strptime(clock_24, '%H:%M').strftime('%I:%M %p').lstrip('0')


def main():
    print('Experiment 8 — LLM-generated candidates; SYNTHETIC evaluation only')
    print('Request:', TEST_QUERY)
    try:
        candidates = generate_llm_candidates(TEST_QUERY)
        checked, best = assess_llm_candidates(candidates)
        for i, (sequence, result) in enumerate(checked, 1):
            status = 'PASS' if result['feasible'] else 'REJECT'
            print(f"Candidate {i}: {' -> '.join(sequence)} | {status} | "
                  f"{result['reason']} | score={result['score']}")
        if best is None:
            print('NO FEASIBLE PLAN — all generated candidates rejected.')
        else:
            sequence, evaluation = best
            print('Selected:', ' -> '.join(sequence))
            print('Synthetic arrivals:', ', '.join(
                f'{task} {display_time(time)}' for task, time in evaluation['timeline']))
            print('These are invented test times, NOT real travel estimates.')
    except Exception as exc:
        print(f'Experiment failed safely: {type(exc).__name__}: {exc}')
        raise SystemExit(1)


if __name__ == '__main__':
    main()
