"""Run integrated MINA v1. Live calls incur OpenAI API charges.

Examples:
  python run_mina_v1.py --no-rag --mode deterministic
  python run_mina_v1.py --no-rag --mode llm
  python run_mina_v1.py --mode llm "Your request here"
"""
import argparse
import json
from time import perf_counter

from mina_audit import append_audit_log, audit_record

from mina_runtime import run_request

DEFAULT = (
    "Tomorrow I need to return library books, buy groceries, and pick up "
    "my daughter from school before 2:30 PM. The library opens at noon, "
    "and grocery shopping must take at least 90 minutes."
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("request", nargs="?", default=DEFAULT)
    parser.add_argument("--mode", choices=["llm", "deterministic"], default="llm")
    parser.add_argument("--no-rag", action="store_true", help="Skip embeddings/retrieval for first smoke test")
    parser.add_argument("--live-tools", action="store_true",
                        help="Opt in to read-only system time and Open-Meteo weather tools")
    parser.add_argument("--city", default=None, metavar="CITY",
                        help="Explicit weather location, e.g. 'Apex, NC'; no automatic location access")
    parser.add_argument("--origin", default=None, metavar="PUBLIC_PLACE",
                        help="Explicit route origin; address or longitude,latitude")
    parser.add_argument("--destination", default=None, metavar="PUBLIC_PLACE",
                        help="Explicit route destination; address or longitude,latitude")
    parser.add_argument("--via", action="append", default=[], metavar="PUBLIC_PLACE",
                        help="Optional intermediate stop; may repeat up to 3 times")
    parser.add_argument("--live-plan", action="store_true",
                        help="Opt-in live route estimates for Complex Planner/Critic; no synthetic schedule defaults")
    parser.add_argument("--start-time", default=None, metavar="TIME",
                        help="Planning start e.g. '10:00 AM' (old HH:MM also accepted)")
    parser.add_argument("--saved-places", default=None, metavar="JSON_PATH",
                        help="Read 12-hour AM/PM task windows from Saved Places JSON (opt-in live plan only)")
    parser.add_argument("--plan-date", default=None, metavar="YYYY-MM-DD",
                        help="Date of planned errands, required for Saved Places weekly hours")
    parser.add_argument("--task-location", action="append", default=[], metavar="TASK=PLACE",
                        help="Public location per task: library, groceries, school_pickup; repeat")
    parser.add_argument("--duration", action="append", default=[], metavar="TASK=MINUTES",
                        help="User-supplied task duration in minutes; repeat for each task")
    parser.add_argument("--library-open", default=None, metavar="TIME",
                        help="User-provided, UNVERIFIED library opening time e.g. '12:00 PM'")
    parser.add_argument("--travel-buffer", type=int, default=10, metavar="MINUTES",
                        help="Safety buffer per routing leg (default 10; not a guarantee)")
    parser.add_argument("--map-output", default="evaluation/maps/latest_route_preview.html", metavar="FILE",
                        help="Local Leaflet HTML preview; never commit it to public GitHub")
    parser.add_argument("--timezone", default=None, metavar="IANA_ZONE",
                        help="Time zone for current-time questions, e.g. America/New_York")
    parser.add_argument(
        "--audit-log", action="store_true",
        help="Append sanitized run metadata as JSONL",
    )
    parser.add_argument(
        "--audit-path", default="evaluation/mina_runs.jsonl", metavar="PATH",
        help="Output JSONL file used with --audit-log",
    )
    args = parser.parse_args()
    if (args.origin or args.destination or args.via) and not args.live_tools:
        parser.error("Route flags require --live-tools")
    if args.live_plan and not args.live_tools:
        parser.error("--live-plan requires --live-tools")
    if not args.live_plan and (args.task_location or args.duration or args.start_time or args.library_open
                               or args.saved_places or args.plan_date):
        parser.error("--task-location, --duration, --start-time, --library-open require --live-plan")
    if args.live_plan and (not args.origin or args.destination or args.via):
        parser.error("--live-plan requires --origin and does not accept --destination/--via")
    if args.live_plan and not args.start_time:
        parser.error("--live-plan requires --start-time (e.g. '10:00 AM')")
    if bool(args.saved_places) != bool(args.plan_date):
        parser.error("--saved-places and --plan-date must be provided together")
    from mina_planning import SUPPORTED
    def parse_items(items, flag, convert=lambda x:x):
        result = {}
        for item in items:
            name, sep, value = item.partition('=')
            if not sep or name not in SUPPORTED or not value.strip() or name in result:
                parser.error(f"Invalid or duplicate {flag}. Use TASK=VALUE for library/groceries/school_pickup")
            try:
                result[name] = convert(value.strip())
            except (TypeError, ValueError):
                parser.error(f"Invalid value for {flag}")
        return result
    live_plan = None
    if args.live_plan:
        from mina_live_planning import LivePlanInputs
        live_plan = LivePlanInputs(
            origin=args.origin,
            task_locations=parse_items(args.task_location, '--task-location'),
            start_time=args.start_time,
            durations=parse_items(args.duration, '--duration', int),
            library_open=args.library_open,
            travel_buffer_minutes=args.travel_buffer,
            saved_places_file=args.saved_places,
            plan_date=args.plan_date,
        )
    route_stops = ((args.origin,) + tuple(args.via) + (args.destination,)) if (
        args.origin and args.destination) else None
    print("MINA v1 integrated | mode:", args.mode, "| RAG:", not args.no_rag)
    print("REQUEST:", args.request)
    started = perf_counter()
    try:
        result = run_request(args.request, planner_mode=args.mode, use_rag=not args.no_rag,
                             live_tools=args.live_tools, city=args.city,
                             timezone_name=args.timezone, route_stops=route_stops,
                             live_plan=live_plan)
    except Exception as exc:
        print("MINA stopped before execution:", type(exc).__name__)
        print("Check your environment or Coordinator output; no plan is claimed.")
        raise SystemExit(1)
    elapsed_ms = (perf_counter() - started) * 1000
    if args.audit_log:
        saved = append_audit_log(args.audit_path, audit_record(
            result, mode=args.mode, rag_enabled=not args.no_rag, elapsed_ms=elapsed_ms
        ))
        print("AUDIT LOG:", saved, "(sanitized metadata only)")
    print("\nSTATUS:", result.status, "| ROUTE:", result.route)
    print("\nTRACE (live read-only sources only if --live-tools; otherwise synthetic):")
    print(json.dumps(result.trace, indent=2, ensure_ascii=False))
    if result.candidates:
        print("\nCANDIDATE CHECKS:")
        for item in result.candidates:
            print(" -", " -> ".join(item["sequence"]), "|",
                  "PASS" if item["feasible"] else "REJECT", "|", item["reason"])
    print("\nMINA:\n", result.answer)
    if result.map_report is not None:
        from mina_route_tools import write_route_map
        try:
            path = write_route_map(result.map_report, args.map_output)
            print("\nLOCAL MAP:", path.resolve())
            print("Open in Finder: open", path.resolve())
        except (ValueError, OSError) as exc:
            print("MAP PREVIEW NOT SAVED:", type(exc).__name__)


if __name__ == "__main__":
    main()
