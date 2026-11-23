"""Local tests: no API calls and no family-note model download required."""
from tot_planner import generate_candidates, select_candidate, format_time


def test_controlled_plan():
    # Test the planner and final-response formatting without loading RAG/LLM modules.
    import ast
    from pathlib import Path
    source = Path(__file__).with_name('mina_agent_tot_integrated.py').read_text()
    tree = ast.parse(source)
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
              and node.name == 'synthetic_plan_answer')
    code = compile(ast.Module(body=[fn], type_ignores=[]), '<extracted-function>', 'exec')
    ns = {"format_time": format_time}
    exec(code, ns)
    checked, best = select_candidate(generate_candidates())
    assert len(checked) == 3 and best is not None
    result = ns['synthetic_plan_answer'](best, [
        {'title': 'Library Holds', 'text': 'Check reserved books'},
        {'title': 'Book Return Bag', 'text': 'Keep books together'},
    ])
    assert 'Return library books' in result
    assert 'Buy groceries' in result
    assert 'Pick up your daughter' in result
    assert 'reserved' not in result.lower()
    assert 'Costco' not in result
    assert 'invented test data' in result
    print('PASS: selected plan controls final response; no added library-hold task.')


if __name__ == '__main__':
    test_controlled_plan()
