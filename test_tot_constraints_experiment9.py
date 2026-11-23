"""Offline regression tests for Experiment 9. No API calls."""
from copy import deepcopy
from tot_constraints_experiment9 import make_fixture, evaluate_constrained, assess

f = make_fixture()
assert f['duration_minutes']['groceries'] == 90
assert f['library_open'] == '12:00'
print('PASS: test fixture applies noon opening and 90-minute shopping duration')

valid = ('groceries', 'library', 'school_pickup')
r = evaluate_constrained(valid, f)
assert r['feasible'], r
assert dict(r['timeline'])['library'] >= '12:00'
assert dict(r['timeline'])['school_pickup'] < '14:30'
print('PASS: feasible candidate obeys library opening and pickup deadline')

early_library = ('library', 'groceries', 'school_pickup')
r = evaluate_constrained(early_library, f)
assert not r['feasible'] and dict(r['timeline'])['library'] == '12:00', r
assert r['reason'] == 'School pickup deadline violated'
print('PASS: early library arrival waits until noon, causing late pickup and rejection')

bad_duration = deepcopy(f)
bad_duration['duration_minutes']['groceries'] = 60
assert not evaluate_constrained(valid, bad_duration)['feasible']
print('PASS: grocery duration under 90 minutes rejected')

late = deepcopy(f)
late['pickup_deadline'] = '12:00'
assert not evaluate_constrained(valid, late)['feasible']
print('PASS: late school pickup rejected')

assert not evaluate_constrained(('library', 'school_pickup'), f)['feasible']
assert not evaluate_constrained(('library', 'groceries', 'school_pickup', 'library_holds'), f)['feasible']
print('PASS: missing and extra tasks rejected')

checked, best = assess([('library', 'school_pickup'),
                        ('library', 'groceries', 'library_holds'),
                        ('school_pickup', 'school_pickup', 'groceries')], f)
assert best is None and all(not r['feasible'] for _, r in checked)
print('PASS: no feasible candidates -> no selection')
print('7/7 offline checks passed; live LLM behavior not tested.')
