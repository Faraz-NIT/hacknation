"""Typed contracts shared by every SkyMentor engine.

Everything that crosses an API boundary or is persisted goes through one of
these Pydantic models, so a malformed agent tool call or LLM output fails
loudly instead of silently corrupting the Work Map.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

CABIN_RANK = {"economy": 0, "premium_economy": 1, "business": 2, "first": 3}

DecisionType = Literal[
    "connection_risk", "customer_deadline", "authority_boundary", "other"
]
EventType = Literal[
    "case_opened",
    "alternative_inspected",
    "alternative_rejected",
    "alternative_selected",
    "escalation_requested",
    "rebook_confirmed",
    "note",
]


# --------------------------------------------------------------------------- case
class Passenger(BaseModel):
    name: str
    pnr: str
    checked_bag: bool
    arrival_deadline: str  # "HH:MM" local, destination day
    deadline_reason: str
    original_cabin: str = "economy"
    tier: str = "none"
    email: Optional[str] = None
    phone: Optional[str] = None


class FlightStatus(BaseModel):
    number: str
    route: str
    disrupted_leg: str
    status: str
    delay_min: Optional[int] = None
    scheduled_arrival: Optional[str] = None
    source: str = "fixture"  # live | cached HH:MM | fixture


class Alternative(BaseModel):
    id: str
    label: str
    hub: str
    hub_city: str
    carrier: str
    alliance: str = ""
    departure: str
    arrival: str
    connection_min: int
    price_eur: int
    cabin: str = "economy"
    seats_left: Optional[int] = None
    note: Optional[str] = None


class Case(BaseModel):
    case_id: str
    title: str
    briefing: str
    origin: str
    destination: str
    flight: FlightStatus
    passenger: Passenger
    alternatives: list[Alternative]
    weather: dict[str, Any] = Field(default_factory=dict)
    market: list[dict[str, Any]] = Field(default_factory=list)  # live public fares (context only)
    provenance: dict[str, str] = Field(default_factory=dict)

    def option(self, option_id: str) -> Alternative:
        for alt in self.alternatives:
            if alt.id == option_id:
                return alt
        raise KeyError(option_id)


# ---------------------------------------------------------------------- sessions
class SessionCreate(BaseModel):
    mode: Literal["expert", "trainee"]
    case_id: Optional[str] = None
    expert_name: str = "Claire"
    expert_session_id: Optional[str] = None
    live: bool = True


class EventIn(BaseModel):
    session_id: str
    type: EventType
    option_id: Optional[str] = None
    detail: dict[str, Any] = Field(default_factory=dict)
    snapshot: dict[str, Any] = Field(default_factory=dict)
    off_record: bool = False


class TranscriptIn(BaseModel):
    session_id: str
    role: Literal["user", "agent", "system"]
    text: str
    off_record: bool = False


# ------------------------------------------------------------------------- rules
class LearnedRule(BaseModel):
    rule_id: str
    session_id: str
    decision_type: DecisionType
    title: str
    condition: dict[str, Any]
    action: Literal["avoid_route", "require_escalation", "note"]
    reason: str
    guardrail: Optional[str] = None
    threshold_min: Optional[int] = None  # connection floor or deadline buffer
    escalation: Optional[str] = None
    exception: Optional[str] = None
    source_event_id: Optional[str] = None
    source_ts: Optional[float] = None
    source_transcript_span: Optional[str] = None
    quote: Optional[str] = None  # the expert's original words (live answer)
    notes: list[str] = Field(default_factory=list)  # debrief answers + corrections, in order
    confidence: float = 0.6
    expert_confirmed: bool = False
    corrections: int = 0
    extracted_by: str = "heuristic"


class RuleRecordIn(BaseModel):
    """Payload of the agent's `record_expert_rule` client tool."""

    session_id: str
    decision_type: DecisionType
    reason: str
    threshold_minutes: Optional[int] = None
    escalation: Optional[str] = None
    exception: Optional[str] = None
    guardrail: Optional[str] = None
    quote: Optional[str] = None
    event_id: Optional[str] = None
    confidence: float = 0.8


class ExtractIn(BaseModel):
    """Free-text answer -> rules (simulated agent, or backfill)."""

    session_id: str
    text: str
    event_id: Optional[str] = None


class GapAnswerIn(BaseModel):
    session_id: str
    gap_id: str
    answer: str = ""
    threshold_minutes: Optional[int] = None
    escalation: Optional[str] = None
    exception: Optional[str] = None


class RuleCorrectionIn(BaseModel):
    session_id: str
    rule_id: Optional[str] = None
    decision_type: Optional[DecisionType] = None  # agent may correct by category
    text: Optional[str] = None  # free-text correction, parsed server-side
    threshold_minutes: Optional[int] = None
    escalation: Optional[str] = None
    exception: Optional[str] = None
    reason: Optional[str] = None
    note: str = ""


class ConfirmIn(BaseModel):
    session_id: str


# --------------------------------------------------------------------- guardrails
class ActionIn(BaseModel):
    session_id: str
    type: Literal["confirm", "select"] = "confirm"
    option_id: str
    has_supervisor_approval: bool = False


class TraineeAnswerIn(BaseModel):
    session_id: str
    kind: Literal["prediction", "explanation"]
    text: str
    rule_id: Optional[str] = None
