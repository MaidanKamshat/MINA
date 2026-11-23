"""Live test of Block 2. This makes ONE paid OpenAI Responses API call."""
import json
import sys
from mina_coordinator import extract_request


def main():
    query = " ".join(sys.argv[1:]).strip() or (
        "Tomorrow I need to return library books, buy groceries, and pick up "
        "my daughter from school before 2:30 PM. The library opens at noon, "
        "and grocery shopping must take at least 90 minutes."
    )
    print("[MINA] Block 2: structured extraction / routing (no planning, no writes)")
    try:
        state = extract_request(query)
    except Exception as exc:
        print(f"[MINA] Stopped safely: {type(exc).__name__}: {exc}")
        raise SystemExit(1)
    print(json.dumps(state.to_dict(), indent=2, ensure_ascii=False))
    print("\nNEXT: Planner/Critic/Controller integration, not yet run by this script.")


if __name__ == "__main__":
    main()
