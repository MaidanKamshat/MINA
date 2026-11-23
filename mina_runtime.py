"""MINA integrated v1: simple/complex branches with selective planning.

No external writes, no real schedule/maps verification. Trace returned for review.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mina_coordinator import extract_request
from mina_write_guard import detect_explicit_write
from mina_state import RequestState
from mina_planning import (
    NeedsClarification, build_context, generate_llm_candidates,
    allowed_sequences, assess_plans, format_plan,
)


@dataclass
class RuntimeResult:
    status: str
    route: str
    answer: str
    trace: list[dict[str, Any]] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    retrieved_notes: list[dict[str, Any]] = field(default_factory=list)
    map_report: Any | None = None  # Read-only route data for local preview; never audit raw coordinates.


def _retrieve(query: str, enabled: bool) -> list[dict[str, Any]]:
    if not enabled:
        return []
    from retrieval import retrieve
    return [n for n in retrieve(query, top_k=3) if n["score"] >= 0.20]


def run_state(
    state: RequestState,
    *,
    client=None,
    planner_mode: str = "llm",
    use_rag: bool = False,
    live_tools: bool = False,
    city: str | None = None,
    timezone_name: str | None = None,
    route_stops: tuple[str, ...] | None = None,
    live_plan=None,
) -> RuntimeResult:
    """Run already-parsed state; offline tests can pass their own state.

    planner_mode='deterministic' avoids LLM candidate-generation calls but
    preserves identical Critic and Controller. Coordinator extraction is separate.
    """
    trace: list[dict[str, Any]] = [{"step": "coordinator", "route": state.route, "intent": state.intent,
                                  "task_ids": [t.task_id for t in state.tasks]}]
    # Mandatory safety gate independent of the Coordinator's model-produced
    # write_action_requested flag. Never run retrieval, planning or write tools
    # for an external mutation request in this read-only MVP.
    must_block_write = (
        state.write_action_requested
        or detect_explicit_write(state.user_request) is not None
        or state.intent in {"list_update", "calendar_update"}
        or any(t.task_id in {"shopping_list_update", "calendar_update"} for t in state.tasks)
    )
    if must_block_write:
        trace.append({"step": "safety", "decision": "no write tools; no modification"})
        return RuntimeResult(
            "approval_required", state.route,
            "I can prepare that change, but no list/calendar/email write tool is connected. "
            "I have not changed or sent anything.", trace,
        )
    # Explicit opt-in mixed-source scheduling. Never use synthetic fixture times
    # for real trip planning. Independent write guard above takes precedence.
    if live_plan is not None:
        if not live_tools:
            raise ValueError('Live planning requires --live-tools')
        if state.route != "complex":
            trace.append({"step": "live_planning", "status": "needs_clarification"})
            return RuntimeResult("needs_clarification", state.route,
                                 "Live multi-stop planning needs at least two recognized schedulable tasks.", trace)
        from mina_live_planning import plan_with_live_routes
        from mina_live_tools import LocationRequired, ToolUnavailable
        try:
            outcome = plan_with_live_routes(state, live_plan, planner_mode=planner_mode, client=client)
            return RuntimeResult(outcome.status, "complex", outcome.answer,
                                 trace + outcome.trace, outcome.candidates, map_report=outcome.map_report)
        except (NeedsClarification, LocationRequired) as exc:
            trace.append({"step": "live_planning", "status": "needs_clarification",
                          "reason_type": type(exc).__name__})
            return RuntimeResult("needs_clarification", "complex", str(exc), trace)
        except ToolUnavailable:
            trace.append({"step": "live_planning", "status": "unavailable", "source": "HeiGIT"})
            return RuntimeResult("tool_unavailable", "complex",
                                 "Routing data could not be verified. No synthetic travel time was substituted; "
                                 "no provisional plan was recommended.", trace)
    # Route-only path: explicitly supplied locations, no inferred private address,
    # no LLM call, and no fallback to made-up travel time if the API fails.
    if live_tools and state.route == "simple":
        from mina_route_routing import is_route_only_query
        if is_route_only_query(state.user_request):
            from mina_live_tools import LocationRequired, ToolUnavailable
            from mina_route_tools import get_route_report, describe_route
            if not route_stops or len(route_stops) < 2:
                trace.append({"step": "live_route", "status": "needs_clarification"})
                return RuntimeResult("needs_clarification", "simple",
                    "Provide explicit --origin and --destination public locations. "
                    "Use --via for intermediate stops. No route was estimated.", trace)
            try:
                report = get_route_report(route_stops)
            except LocationRequired as exc:
                trace.append({"step": "live_route", "status": "needs_clarification"})
                return RuntimeResult("needs_clarification", "simple", str(exc), trace)
            except ToolUnavailable:
                trace.append({"step": "live_route", "status": "unavailable", "source": "HeiGIT"})
                return RuntimeResult("tool_unavailable", "simple",
                    "The real route could not be verified. No synthetic travel estimate was substituted.", trace)
            trace.append({"step": "live_route", "status": "ok", "source": "HeiGIT",
                          "count": len(report.stops)})
            return RuntimeResult("simple_response", "simple", describe_route(report), trace,
                                 map_report=report)
    # Opt-in live read-only tools, never executed during the original benchmark.
    # The critical write gate above always runs before any external read.
    if live_tools and state.route == "simple":
        from mina_live_routing import simple_live_topics, requested_weather_day
        from mina_live_tools import (LocationRequired, ToolUnavailable,
                                     get_weather_report, describe_weather, current_local_time)
        weather, clock = simple_live_topics(state.user_request)
        if weather or clock:
            outputs = []
            try:
                if clock:
                    outputs.append(current_local_time(timezone_name))
                    trace.append({"step": "live_time", "status": "ok", "source": "system_clock"})
                if weather:
                    if not city:
                        raise LocationRequired("Please specify a city with --city, e.g. 'Apex, NC'.")
                    day = requested_weather_day(state.user_request)
                    report = get_weather_report(city, day=day)
                    outputs.append(describe_weather(report))
                    trace.append({"step": "live_weather", "status": "ok", "source": "Open-Meteo",
                                  "date": report.date, "timezone": report.timezone})
            except LocationRequired as exc:
                trace.append({"step": "live_tools", "status": "needs_clarification",
                              "reason_type": type(exc).__name__})
                return RuntimeResult("needs_clarification", "simple",
                                     " ".join(outputs + [str(exc)]), trace)
            except ToolUnavailable:
                trace.append({"step": "live_tools", "status": "unavailable", "source": "Open-Meteo"})
                return RuntimeResult("tool_unavailable", "simple",
                                     " ".join(outputs + ["Current weather could not be verified. "
                                                         "No forecast was invented; try again later."]), trace)
            return RuntimeResult("simple_response", "simple", " ".join(outputs), trace)
    try:
        notes = _retrieve(state.user_request, use_rag)
    except Exception as exc:
        trace.append({"step": "retrieval", "status": "failed", "error_type": type(exc).__name__})
        return RuntimeResult("needs_clarification", state.route,
                             "Family context retrieval is unavailable, so I cannot rely on saved preferences.", trace)
    trace.append({"step": "retrieval", "note_ids": [x["id"] for x in notes]})
    if state.route != "complex":
        if client is None:
            # In test mode, no invented weather or calendar responses.
            answer = "Your request was recognized. No live tools or external writes were executed."
        else:
            response = client.responses.create(
                model="gpt-4.1-mini",
                instructions=(
                    "You are MINA. Give a concise answer based only on the user request "
                    "and the provided synthetic family notes. Never add errands or "
                    "claim real-time calendar, travel, or weather facts. No write tools are available."
                ),
                input=f"User request: {state.user_request}\nFamily notes: " +
                      "\n".join(n["text"] for n in notes),
            )
            answer = response.output_text or "I cannot answer reliably with the available information."
        return RuntimeResult("simple_response", "simple", answer, trace, retrieved_notes=notes)

    try:
        context = build_context(state)
        trace.append({"step": "context", "source": context.provenance,
                      "start": context.start, "deadlines": context.deadlines,
                      "library_open": context.library_open, "durations": context.durations})
        if planner_mode == "llm":
            candidates = generate_llm_candidates(state, context, client, notes)
            trace.append({"step": "planner", "method": "LLM", "count": len(candidates)})
        elif planner_mode == "deterministic":
            candidates = allowed_sequences(state)
            trace.append({"step": "planner", "method": "bounded deterministic search",
                          "count": len(candidates)})
        else:
            raise ValueError("Unknown planner mode")
        checked, best = assess_plans(state, context, candidates)
        trace.append({"step": "critic", "passed": sum(c["feasible"] for c in checked),
                      "evaluated": len(checked)})
        if best is None:
            trace.append({"step": "controller", "decision": "no feasible candidate"})
            return RuntimeResult(
                "no_feasible_plan", "complex",
                "No feasible plan under the SYNTHETIC fixture constraints. "
                "I cannot recommend a schedule; please revise the deadline or tasks.",
                trace, checked, notes,
            )
        trace.append({"step": "controller", "decision": "selected", "sequence": best["sequence"],
                      "score": best["score"]})
        return RuntimeResult("synthetic_plan", "complex", format_plan(best, context),
                             trace, checked, notes)
    except NeedsClarification as exc:
        trace.append({"step": "fallback", "reason": str(exc)})
        return RuntimeResult("needs_clarification", "complex",
                             f"I need clarification or a verified context source: {exc}", trace,
                             retrieved_notes=notes)
    except (ValueError, KeyError, TypeError) as exc:
        trace.append({"step": "fallback", "reason_type": type(exc).__name__})
        return RuntimeResult("generation_failed", "complex",
                             "The planner produced an invalid or incomplete result. "
                             "No schedule has been recommended.", trace, retrieved_notes=notes)


def run_request(
    request: str,
    *,
    client=None,
    planner_mode: str = "llm",
    use_rag: bool = True,
    live_tools: bool = False,
    city: str | None = None,
    timezone_name: str | None = None,
    route_stops: tuple[str, ...] | None = None,
    live_plan=None,
) -> RuntimeResult:
    """Live endpoint: Coordinator then selected simple/complex branch."""
    if live_plan is not None and not live_tools:
        raise ValueError("Live plan requires live-tools opt-in")
    if live_tools and live_plan is None:
        from mina_route_routing import is_route_only_query
        from mina_write_guard import detect_explicit_write
        if is_route_only_query(request) and detect_explicit_write(request) is None:
            state = RequestState(user_request=request, intent="information", route="simple",
                                 route_reason="read-only route with explicitly supplied places")
            return run_state(state, client=client, planner_mode=planner_mode,
                             use_rag=use_rag, live_tools=True, city=city,
                             timezone_name=timezone_name, route_stops=route_stops)
        from mina_live_routing import simple_live_topics
        from mina_write_guard import detect_explicit_write
        from mina_state import RequestedTask
        weather, clock = simple_live_topics(request)
        if (weather or clock) and detect_explicit_write(request) is None:
            tasks = [RequestedTask("weather_lookup", "Read weather forecast", request)] if weather else []
            if clock:
                tasks.append(RequestedTask("other", "Read local system time", request))
            state = RequestState(user_request=request, intent="information", tasks=tasks,
                                 route="simple", route_reason="deterministic read-only live-tools fast path")
            return run_state(state, client=client, planner_mode=planner_mode,
                             use_rag=use_rag, live_tools=True, city=city,
                             timezone_name=timezone_name)
    state = extract_request(request, client=client)
    if state.route == "simple" and not state.write_action_requested and client is None:
        from dotenv import load_dotenv
        from pathlib import Path
        from openai import OpenAI
        load_dotenv(Path(__file__).parent / ".env", override=True)
        client = OpenAI()
    return run_state(state, client=client, planner_mode=planner_mode, use_rag=use_rag,
                     live_tools=live_tools, city=city, timezone_name=timezone_name,
                     live_plan=live_plan)
