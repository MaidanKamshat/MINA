"""Experiment 9: controlled additional constraints; no live time or maps.

Reuse Experiment 8 LLM generator, but evaluate with an expanded deterministic
critic. All durations, opening times, and travel estimates are synthetic.
"""
from copy import deepcopy
from tot_planner import TASKS, FIXTURE, minutes, clock
from tot_llm_generator import generate_llm_candidates, display_time

QUERY = ("Tomorrow I need to return library books, buy groceries, and pick up "
         "my daughter before 2:30 PM. The library doesn't open until noon, "
         "and grocery shopping must take at least 90 minutes.")


def make_fixture():
    fixture = deepcopy(FIXTURE)
    fixture['library_open'] = '12:00'
    fixture['duration_minutes']['groceries'] = 90
    return fixture


def evaluate_constrained(sequence, fixture):
    if len(sequence) != len(TASKS) or set(sequence) != set(TASKS):
        return {'feasible': False, 'reason': 'Missing, duplicated, or extra tasks', 'score': None}
    if fixture['duration_minutes']['groceries'] < 90:
        return {'feasible': False, 'reason': 'Grocery duration below required 90 minutes', 'score': None}
    now = minutes(fixture['start'])
    prev = 'start'
    travel_total = waiting_total = 0
    timeline = []
    for task in sequence:
        travel = fixture['travel_minutes'].get((prev, task))
        if travel is None:
            return {'feasible': False, 'reason': 'Unknown travel duration', 'score': None}
        now += travel
        travel_total += travel
        if task == 'library':
            opening = minutes(fixture['library_open'])
            if now < opening:
                waiting_total += opening - now
                now = opening
        if task == 'school_pickup':
            if now >= minutes(fixture['pickup_deadline']):
                return {'feasible': False, 'reason': 'School pickup deadline violated', 'score': None,
                        'timeline': timeline + [(task, clock(now))]}
            window = minutes(fixture['pickup_window_start'])
            if now < window:
                waiting_total += window - now
                now = window
        timeline.append((task, clock(now)))
        now += fixture['duration_minutes'][task]
        prev = task
    return {'feasible': True, 'reason': 'Opening, duration, task set, and pickup deadline satisfied',
            'score': 300 - travel_total - waiting_total,
            'timeline': timeline, 'waiting_minutes': waiting_total}


def assess(candidates, fixture=None):
    fixture = make_fixture() if fixture is None else fixture
    checked = [(tuple(c), evaluate_constrained(tuple(c), fixture)) for c in candidates]
    feasible = [(c, result) for c, result in checked if result['feasible']]
    return checked, max(feasible, key=lambda item: item[1]['score']) if feasible else None


def main():
    fixture = make_fixture()
    print('Experiment 9 — additional constraints; SYNTHETIC data only')
    print('Request:', QUERY)
    print('Synthetic start:', display_time(fixture['start']))
    print('Synthetic library opening:', display_time(fixture['library_open']))
    print('Minimum grocery duration: 90 minutes')
    print('Synthetic pickup window:', display_time(fixture['pickup_window_start']),
          'to', display_time(fixture['pickup_deadline']), '(deadline exclusive)')
    try:
        candidates = generate_llm_candidates(QUERY)
    except Exception as exc:
        print(f'LLM generation failed: {type(exc).__name__}: {exc}')
        raise SystemExit(1)
    checked, best = assess(candidates, fixture)
    for i, (candidate, result) in enumerate(checked, 1):
        print(f"Candidate {i}: {' -> '.join(candidate)} | "
              f"{'PASS' if result['feasible'] else 'REJECT'} | "
              f"{result['reason']} | score={result['score']}")
    if best is None:
        print('NO FEASIBLE PLAN among the three candidates; do not invent a valid schedule.')
    else:
        sequence, result = best
        print('Selected:', ' -> '.join(sequence))
        print('Synthetic arrivals:', ', '.join(
            f'{task} {display_time(time)}' for task, time in result['timeline']))
    print('No actual route, calendar, or library opening data were consulted.')


if __name__ == '__main__':
    main()
