"""Debrief: gaps come from missing rule fields, not from the model's imagination.

`compute_gaps` is a validator over the typed rules. The debrief is "done" when
no mandatory gap remains, at least three follow-ups were answered (or nothing is
left to ask) and the expert confirmed the teach-back.
"""
from __future__ import annotations

from typing import Any

from ..models import Case, LearnedRule
from .rules import hhmm, risk_flags

MIN_DEBRIEF_QUESTIONS = 3


def _present_categories(case: Case) -> set[str]:
    cats = set()
    for alt in case.alternatives:
        for flag in risk_flags(case, alt):
            cats.add({"short_connection_with_bag": "connection_risk", "after_deadline": "customer_deadline",
                      "cabin_change": "authority_boundary"}[flag])
    return cats


def compute_gaps(case: Case, rules: list[LearnedRule], state: dict[str, Any]) -> list[dict[str, Any]]:
    answered = set(state.get("answered_gaps", []))
    gaps: list[dict[str, Any]] = []
    by_type = {r.decision_type: r for r in rules}
    dl = case.passenger.arrival_deadline
    early = hhmm(dl) - 10
    near = f"{early // 60}:{early % 60:02d}"

    def add(gap_id, question, mandatory, category, rule_id=None, field=None):
        if gap_id not in answered:
            gaps.append({"gap_id": gap_id, "question": question, "mandatory": mandatory,
                         "category": category, "rule_id": rule_id, "field": field})

    r = by_type.get("connection_risk")
    if r:
        if not r.threshold_min:
            add(f"{r.rule_id}:threshold", "You ruled out a tight connection. What is the shortest connection you would accept when a bag is checked?",
                True, "connection_risk", r.rule_id, "threshold")
        if not r.exception:
            add(f"{r.rule_id}:exception", "Is there any case where you'd accept a shorter connection, say carry-on only or a same-terminal transfer?",
                False, "connection_risk", r.rule_id, "exception")
    r = by_type.get("customer_deadline")
    if r:
        if not r.threshold_min:
            add(f"{r.rule_id}:threshold", f"For the {dl} deadline, how much margin do you need? Would landing at {near} be acceptable?",
                True, "customer_deadline", r.rule_id, "threshold")
        if not r.exception:
            add(f"{r.rule_id}:exception", "Would you ever book a later arrival, for example if the passenger agrees to it?",
                False, "customer_deadline", r.rule_id, "exception")
    r = by_type.get("authority_boundary")
    if r:
        if not r.escalation:
            add(f"{r.rule_id}:escalation", "When a cabin change is the only option, who exactly do you go to for approval?",
                True, "authority_boundary", r.rule_id, "escalation")
        if not r.exception:
            add(f"{r.rule_id}:exception", "Is there any cabin change you can approve on your own, for example for a status passenger?",
                False, "authority_boundary", r.rule_id, "exception")

    missing = {
        "connection_risk": "I didn't hear a rule about connection times. With a checked bag, what's the shortest connection you'd book?",
        "customer_deadline": "How do you treat the passenger's arrival deadline when the cheapest option lands late?",
        "authority_boundary": "If only business class were left, could you book it yourself? Who would you ask?",
    }
    for cat in sorted(_present_categories(case)):
        if cat not in by_type:
            add(f"missing:{cat}", missing[cat], True, cat, None, "rule")

    add("unseen:no_bag", "A case I haven't seen: what changes if the passenger has carry-on only?", False, "unseen")
    add("unseen:weather", "Would bad weather at the connecting hub change which connection you accept?", False, "unseen")

    gaps.sort(key=lambda g: (not g["mandatory"]))
    return gaps


def status(case: Case, rules: list[LearnedRule], state: dict[str, Any]) -> dict[str, Any]:
    gaps = compute_gaps(case, rules, state)
    mandatory_left = [g for g in gaps if g["mandatory"]]
    n_answered = len(state.get("answered_gaps", []))
    ready = not mandatory_left and (n_answered >= MIN_DEBRIEF_QUESTIONS or not gaps)
    return {
        "gaps": gaps,
        "mandatory_open": len(mandatory_left),
        "answered": n_answered,
        "min_questions": MIN_DEBRIEF_QUESTIONS,
        "ready_for_teachback": ready,
        "teachback": teachback(case, rules, state) if ready else None,
        "teachback_confirmed": bool(state.get("teachback_confirmed")),
        "complete": ready and bool(state.get("teachback_confirmed")),
        "corrections": int(state.get("corrections", 0)),
    }


def teachback(case: Case, rules: list[LearnedRule], state: dict[str, Any]) -> str:
    by = {r.decision_type: r for r in rules}
    parts = ["Here's how I understand it. When a passenger's flight is disrupted, you first check their constraints: "
             "checked bag, arrival deadline and the cabin they paid for."]
    if (r := by.get("connection_risk")):
        exc = f" The exception: {r.exception}." if r.exception and not r.exception.startswith("none") else ""
        parts.append(f"With a checked bag, you never book a connection under {r.threshold_min or '?'} minutes, "
                     f"because the bag or the passenger misses the transfer.{exc}")
    if (r := by.get("customer_deadline")):
        margin = f" with at least {r.threshold_min} minutes of margin" if r.threshold_min else ""
        parts.append(f"You rule out anything that lands after the passenger's deadline{margin}, even when it's cheaper.")
    if (r := by.get("authority_boundary")):
        parts.append(f"If the only workable option is a higher cabin, you stop and get approval from "
                     f"{r.escalation or 'a supervisor'} before ticketing; you never upgrade on your own.")
    parts.append("Among what's left, you pick the most reliable option, not simply the cheapest or the earliest. Is that right?")
    return " ".join(parts)
