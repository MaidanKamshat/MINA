"""MINA experimental complexity router, version 2.

Heuristic only; 'tot_candidate' does not execute ToT.
"""
import re

ACTIVITY_PATTERNS = {
    "library": r"\b(librar(?:y|ies)|return (?:the )?books?)\b",
    "shopping": r"\b(grocer(?:y|ies)|shop(?:ping)?|costco|target|buy|purchase)\b",
    "school": r"\b(school|daycare|preschool|pick[ -]?up|drop[ -]?off)\b",
    "appointment": r"\b(appointment|doctor|dentist|pediatrician)\b",
    "meal": r"\b(cook|dinner|lunch|breakfast|meal prep)\b",
    "household": r"\b(laundry|clean(?:ing)?|chores?)\b",
}
DEADLINE = r"\b(before|by|no later than|deadline)\b|\bat\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)\b"
PLANNING = r"\b(plan|organize|schedule|coordinate|fit in|combine|route|itinerary)\b"
CONFLICT = r"\b(conflict|overlap|same time|can't make|cannot make)\b"


def assess_complexity(request: str) -> dict:
    q = request.lower()
    activities = [name for name, pattern in ACTIVITY_PATTERNS.items()
                  if re.search(pattern, q, flags=re.I)]
    deadline = bool(re.search(DEADLINE, q, flags=re.I))
    planning = bool(re.search(PLANNING, q, flags=re.I))
    conflict = bool(re.search(CONFLICT, q, flags=re.I))
    score = 2 if len(activities) >= 2 else 0
    score += 2 if deadline else 0
    score += 2 if planning and len(activities) >= 2 else 0
    score += 3 if conflict else 0
    # V2: 3+ categories with a deadline are a ToT candidate even without 'plan'.
    multi_task_deadline = len(activities) >= 3 and deadline
    strategy = "tot_candidate" if score >= 5 or multi_task_deadline else "direct"
    return {
        "strategy": strategy, "score": score,
        "signals": {"activities": activities, "deadline_mentioned": deadline,
                    "planning_requested": planning, "conflict_mentioned": conflict,
                    "multi_task_deadline_override": multi_task_deadline},
    }

if __name__ == "__main__":
    cases = [
        ("Add milk to my grocery list.", "direct"),
        ("Help me plan tomorrow. I need to return library books and do some grocery shopping.", "direct"),
        ("Tomorrow I need to return library books, buy groceries, and pick up my daughter from school before 2:30 PM.", "tot_candidate"),
        ("Plan library returns and groceries before school pickup at 2:30 PM.", "tot_candidate"),
        ("What's the weather tomorrow?", "direct"),
    ]
    for query, expected in cases:
        result = assess_complexity(query)
        print(f"{result['strategy']:13} score={result['score']} expected={expected:13} | {query}")
        assert result["strategy"] == expected, (query, result)
    print("All 5 heuristic smoke tests passed.")
