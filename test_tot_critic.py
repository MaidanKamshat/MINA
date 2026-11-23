"""Experiment 7: robustness checks for MINA's deterministic ToT critic.

Run from the directory containing tot_planner.py:
    python test_tot_critic.py

All clock and travel data are synthetic; no external APIs are used.
"""
from copy import deepcopy
from tot_planner import FIXTURE, evaluate_candidate, generate_candidates, select_candidate

VALID = ("library", "groceries", "school_pickup")


def check(label, sequence, expected, fixture=None, reason_contains=None):
    result = evaluate_candidate(sequence, FIXTURE if fixture is None else fixture)
    actual = "PASS" if result["feasible"] else "REJECT"
    assert actual == expected, f"{label}: expected {expected}, got {actual}: {result}"
    if reason_contains:
        assert reason_contains.lower() in result["reason"].lower(), result
    print(f"{label}: {actual} | {result['reason']}")
    return result


def main():
    print("Experiment 7 — Critic robustness (SYNTHETIC data only)\n")
    check("A — Missing required task", ("library", "school_pickup"), "REJECT", reason_contains="Missing")
    check("B — Unrequested extra task", ("library", "library_holds", "groceries", "school_pickup"), "REJECT", reason_contains="extra")
    late = deepcopy(FIXTURE)
    # All candidates will arrive after 2:30 PM when the scenario starts at 2:40 PM.
    late["start"] = "14:40"
    check("C — Deadline violation", VALID, "REJECT", fixture=late, reason_contains="deadline")
    check("D — Valid plan", VALID, "PASS")

    # Controller must not select an invalid candidate when none is feasible.
    invalid_candidates = [
        ("library", "school_pickup"),
        ("library", "library_holds", "groceries", "school_pickup"),
    ]
    checked, best = select_candidate(invalid_candidates)
    assert best is None, f"Controller selected an invalid plan: {best}"
    assert all(not result["feasible"] for _, result in checked)
    print("E — Controller, no feasible candidates: NO_FEASIBLE_PLAN")

    # Validate all generated plans independently against an impossible fixture.
    assert all(not evaluate_candidate(candidate, late)["feasible"] for candidate in generate_candidates())
    print("F — All generated candidates violate deadline: ALL REJECTED")
    print("\n6/6 checks passed. This validates code behavior under synthetic fixtures, not real-world routing.")


if __name__ == "__main__":
    main()
