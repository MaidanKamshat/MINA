"""MINA checkpoint 4: deterministic one-level ToT experiment.

Synthetic fixture ONLY. No real calendar, location, maps or library APIs.
Generator -> Critic -> Controller. Does not modify user data.
"""
from datetime import datetime

def format_time(time_24h):
    return datetime.strptime(time_24h, "%H:%M").strftime("%I:%M %p").lstrip("0")

TASKS = ("library", "groceries", "school_pickup")
# Entirely invented durations, for controlled testing rather than real-world claims.
FIXTURE = {
    "start": "10:00", "pickup_window_start": "14:00", "pickup_deadline": "14:30",
    "duration_minutes": {"library": 30, "groceries": 60, "school_pickup": 15},
    "travel_minutes": {
        ("start", "library"): 20, ("start", "groceries"): 25,
        ("start", "school_pickup"): 25,
        ("library", "groceries"): 20, ("groceries", "library"): 20,
        ("library", "school_pickup"): 25, ("groceries", "school_pickup"): 20,
        ("school_pickup", "library"): 25, ("school_pickup", "groceries"): 20,
    },
}



def minutes(clock):
    hour, minute = map(int, clock.split(":"))
    return hour * 60 + minute


def clock(total):
    return f"{total // 60:02d}:{total % 60:02d}"


def generate_candidates():
    """Generate three distinct full sequences; school pickup remains included."""
    return [
        ("library", "groceries", "school_pickup"),
        ("groceries", "library", "school_pickup"),
        ("school_pickup", "library", "groceries"),
    ]


def evaluate_candidate(sequence, fixture=FIXTURE):
    required = set(TASKS)
    if len(sequence) != len(TASKS) or set(sequence) != required:
        return {"feasible": False, "reason": "Missing, duplicated, or extra tasks", "score": None}
    now = minutes(fixture["start"])
    previous = "start"
    timeline = []
    travel_total = 0
    waiting_total = 0
    for task in sequence:
        travel = fixture["travel_minutes"].get((previous, task))
        if travel is None:
            return {"feasible": False, "reason": "Unknown travel duration", "score": None}
        travel_total += travel
        now += travel
        arrival = now
        if task == "school_pickup" and arrival >= minutes(fixture["pickup_deadline"]):
            return {"feasible": False, "reason": "School pickup deadline violated", "score": None,
                    "timeline": timeline + [(task, clock(arrival))]}
        if task == "school_pickup" and arrival < minutes(fixture["pickup_window_start"]):
            waiting_total += minutes(fixture["pickup_window_start"]) - arrival
            arrival = minutes(fixture["pickup_window_start"])
            now = arrival
        timeline.append((task, clock(arrival)))
        now += fixture["duration_minutes"][task]
        previous = task
    # With identical required tasks, minimize travel and idle waiting.
    return {"feasible": True, "reason": "All required tasks and pickup deadline satisfied",
            "score": 300 - travel_total - waiting_total, "travel_minutes": travel_total,
            "waiting_minutes": waiting_total, "timeline": timeline}


def select_candidate(candidates):
    checked = [(candidate, evaluate_candidate(candidate)) for candidate in candidates]
    feasible = [(candidate, result) for candidate, result in checked if result["feasible"]]
    best = max(feasible, key=lambda item: item[1]["score"]) if feasible else None
    return checked, best


def run_tot_demo():
    checked, best = select_candidate(generate_candidates())
    lines = ["[ToT DEMO] Synthetic fixture — NOT actual travel times or verified schedule.",
             f"Start {FIXTURE['start']}; synthetic pickup window {FIXTURE['pickup_window_start']}–{FIXTURE['pickup_deadline']} (deadline exclusive)."]
    for index, (candidate, result) in enumerate(checked, 1):
        lines.append(f"Candidate {index}: {' -> '.join(candidate)} | "
                     f"{'PASS' if result['feasible'] else 'PRUNED'} | "
                     f"{result['reason']}" +
                     (f" | score={result['score']}" if result['score'] is not None else ""))
    if best:
        candidate, result = best
        lines.append("Selected (synthetic): " + " -> ".join(candidate))
        lines.append("Synthetic arrival times: " + ", ".join(f"{task} {format_time(time)}" for task, time in result["timeline"]))
    else:
        lines.append("No feasible candidate; ask for updated constraints instead of inventing a plan.")
    lines.append("No Costco or library-hold tasks were introduced; no real-world feasibility is claimed.")
    return "\n".join(lines)


if __name__ == "__main__":
    print(run_tot_demo())
    assert len(generate_candidates()) == 3
    assert all(set(c) == set(TASKS) for c in generate_candidates())
    assert evaluate_candidate(("library", "groceries"))["reason"] == "Missing, duplicated, or extra tasks"
    impossible = {**FIXTURE, "pickup_window_start": "10:00", "pickup_deadline": "10:05"}
    assert all(not evaluate_candidate(c, impossible)["feasible"] for c in generate_candidates())
    print("\nAll ToT prototype smoke tests passed.")
