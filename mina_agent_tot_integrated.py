"""MINA Checkpoint 4 — Experiment 6: integrated, controlled ToT output.

This is a deterministic ONE-LEVEL search using a SYNTHETIC fixture, not real
scheduling. Only the exact three-task test scenario is supported by ToT.
All other requests fall back to the existing RAG assistant.
"""
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from retrieval import retrieve
from complexity_router import assess_complexity
from tot_planner import generate_candidates, select_candidate, FIXTURE
from tot_planner import format_time

load_dotenv(Path(__file__).parent / '.env')
MODEL = 'gpt-4.1-mini'
TOP_K = 3
SIMILARITY_THRESHOLD = 0.20

SYSTEM_INSTRUCTIONS = (
    'You are MINA, a family planning assistant. Prioritize the current request. '
    'Retrieved notes are background, not confirmed current intentions. '
    'Do not add errands or follow-up questions solely because a note mentions them. '
    'Offer a useful provisional plan, then at most one essential clarification. '
    'Do not assume Costco is selected. Never invent travel times, opening hours, '
    'due dates, or appointments. Do not claim tool use or action completion.'
    'All user-facing times must be displayed in 12-hour AM/PM format. Use timezone-aware datetime objects for internal calculations. '
)


def relevant_context(query):
    notes = [n for n in retrieve(query, top_k=TOP_K)
             if n['score'] >= SIMILARITY_THRESHOLD]
    return notes


def supported_fixture(signals, query):
    """Only run the fixture when all three categories and the 2:30 deadline match.

    This guard avoids applying invented pickup times to unrelated user requests.
    """
    import re
    activities = set(signals.get('activities', []))
    has_pickup = bool(re.search(r'pick[ -]?up', query, re.I))
    has_230 = bool(re.search(r'\b2:30\s*(?:pm|p\.m\.)\b', query, re.I))
    return {'library', 'shopping', 'school'}.issubset(activities) and has_pickup and has_230


def synthetic_plan_answer(best, notes):
    """Generate the USER-FACING plan from the evaluated candidate, not an LLM rewrite.

    This is a structural safeguard: no unrelated library-hold task can be inserted.
    """
    sequence, evaluation = best
    labels = {'library': 'Return library books',
              'groceries': 'Buy groceries',
              'school_pickup': 'Pick up your daughter from school'}
    arrival = dict(evaluation['timeline'])
    lines = [
        'Here is the selected PROVISIONAL plan for the synthetic test scenario:',
        '(Times below are invented test data, NOT verified real-world travel or scheduling.)',
    ]
    for i, task in enumerate(sequence, 1):
        lines.append(f'{i}. {labels[task]} — simulated arrival {format_time(arrival[task])}.')
    lines.append('The simulated school pickup arrival is before the 2:30 PM deadline.')
    if any(n['title'] == 'Book Return Bag' for n in notes):
        lines.append('Preparation tip: put your library books in your return bag.')
    lines.append('No store or library branch has been selected, and no real travel times have been checked.')
    lines.append('To make a real plan, we would need your chosen grocery store and verified route/schedule information.')
    return '\n'.join(lines)


def ask_mina(query, client=None):
    routing = assess_complexity(query)
    print(f"\n[Complexity Router] score={routing['score']} "
          f"strategy={routing['strategy']} signals={routing['signals']}")
    notes = relevant_context(query)
    print('\nRetrieved context:')
    for n in notes:
        print(f"- {n['title']}: {n['text']}")
    if not notes:
        print('(none above similarity threshold)')

    if routing['strategy'] == 'tot_candidate' and supported_fixture(routing['signals'], query):
        checked, best = select_candidate(generate_candidates())
        print('\n[ToT — controlled synthetic evaluation]')
        for i, (candidate, result) in enumerate(checked, 1):
            print(f"Candidate {i}: {' -> '.join(candidate)} | "
                  f"{'PASS' if result['feasible'] else 'PRUNED'} | score={result['score']}")
        if best:
            print('Selected:', ' -> '.join(best[0]))
            print('[Output control] Final answer assembled from the selected candidate; '
                  'retrieved notes cannot add new tasks.')
            return synthetic_plan_answer(best, notes)
        return 'No feasible plan in the synthetic fixture. Please revise the constraints.'

    print('[Notice] No matching ToT fixture; using existing RAG response path.')
    context = '\n'.join(f"- {n['title']}: {n['text']}" for n in notes) or 'No relevant notes.'
    client = client or OpenAI()
    response = client.responses.create(
        model=MODEL, instructions=SYSTEM_INSTRUCTIONS,
        input=f'User request:\n{query}\n\nFamily preference context:\n{context}',
    )
    return response.output_text


def main():
    print("\nWelcome to MINA! Type 'exit' to quit.\n")
    while True:
        try:
            query = input('You: ').strip()
        except (KeyboardInterrupt, EOFError):
            print('\nMINA: Goodbye!')
            break
        if query.lower() in ('exit', 'quit'):
            print('MINA: Goodbye!')
            break
        if query:
            try:
                print('\nMINA: ' + ask_mina(query) + '\n')
            except Exception as exc:
                print(f'\nError: {exc}\n')


if __name__ == '__main__':
    main()
