"""Typed request state for MINA's selective simple/complex routing.

Phase 2 only: no calendar writes, no route verification, no planning execution.
"""
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class RequestedTask:
    task_id: str
    description: str
    evidence: str  # exact text excerpt from this request, not retrieved notes


@dataclass(frozen=True)
class Constraint:
    kind: str
    task_id: str | None
    value: str
    evidence: str  # exact text excerpt from this request


@dataclass
class RequestState:
    user_request: str
    intent: str
    tasks: list[RequestedTask] = field(default_factory=list)
    constraints: list[Constraint] = field(default_factory=list)
    preferences: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    write_action_requested: bool = False
    route: str = "simple"
    route_reason: str = ""
    router_signals: dict[str, Any] = field(default_factory=dict)
    status: str = "parsed_not_executed"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
