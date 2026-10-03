"""Decision intelligence: when is an expert action worth a live question?

Q = 0.30*novelty + 0.25*decision_importance + 0.25*alternative_gap + 0.20*knowledge_uncertainty

A question is queued only when Q >= threshold, the live-question budget is not
spent and the event is on the record. *When* it is spoken is decided by the
frontend turn gate (speech + activity idle), never by this module.
"""
from __future__ import annotations

from typing import Any, Optional

from ..models import Case, LearnedRule
from .rules import risk_flags

THRESHOLD = 0.6
MAX_LIVE_QUESTIONS = 5

IMPORTANCE = {
    "rebook_confirmed": 1.0, "escalation_requested": 1.0, "alternative_selected": 0.8,
    "alternative_rejected": 0.8, "alternative_inspected": 0.2, "case_opened": 0.0, "note": 0.1,
}
FLAG_TO_CATEGORY = {
    "short_connection_with_bag": "connection_risk",
    "after_deadline": "customer_deadline",
    "cabin_change": "authority_boundary",
}
GUARDRAIL_CATEGORIES = {"connection_risk", "authority_boundary"}


def _extremes(case: Case) -> tuple[str, str]:
    cheapest = min(case.alternatives, key=lambda a: a.price_eur).id
    earliest = min(case.alternatives, key=lambda a: a.arrival).id
    return cheapest, earliest


def score_event(
    case: Case,
    event_type: str,
    option_id: Optional[str],
    rules: list[LearnedRule],
    asked: list[dict[str, Any]],
    off_record: bool = False,
) -> dict[str, Any]:
    cheapest, earliest = _extremes(case)
    importance = IMPORTANCE.get(event_type, 0.1)
    gap = 0.0
    hypotheses: list[str] = []
    opt = case.option(option_id) if option_id else None

    if opt is not None:
        own_flags = [FLAG_TO_CATEGORY[f] for f in risk_flags(case, opt)]
        attractive = opt.id in (cheapest, earliest)
        if event_type == "alternative_rejected":
            gap = 1.0 if attractive else (0.7 if own_flags else 0.4)
            hypotheses = own_flags
        elif event_type in ("alternative_selected", "rebook_confirmed"):
            is_c, is_e = opt.id == cheapest, opt.id == earliest
            gap = 0.1 if (is_c and is_e) else (0.5 if (is_c or is_e) else 1.0)
            # What made the expert pass over the more attractive options?
            for other in case.alternatives:
                if other.id != opt.id and other.id in (cheapest, earliest):
                    hypotheses += [FLAG_TO_CATEGORY[f] for f in risk_flags(case, other)]
            hypotheses += own_flags  # e.g. confirming a cabin change
        elif event_type == "escalation_requested":
            gap = 1.0
            hypotheses = ["authority_boundary"]
        elif event_type == "alternative_inspected":
            gap = 0.3 if own_flags else 0.1
            hypotheses = own_flags
    hypotheses = list(dict.fromkeys(hypotheses))

    captured = {r.decision_type for r in rules}
    asked_cats = {q["category"] for q in asked}
    open_cats = [c for c in hypotheses if c not in captured and c not in asked_cats]
    novelty = 1.0 if open_cats else (0.2 if hypotheses else 0.0)
    uncertainty = 1.0 if any(c not in captured for c in hypotheses) else (0.1 if hypotheses else 0.3)

    q = round(0.30 * novelty + 0.25 * importance + 0.25 * gap + 0.20 * uncertainty, 3)
    live_asked = [x for x in asked if x.get("phase") == "live"]
    reasons = []
    if off_record:
        reasons.append("off the record")
    if len(live_asked) >= MAX_LIVE_QUESTIONS:
        reasons.append("live-question budget spent (ask less, later)")
    if q < THRESHOLD:
        reasons.append(f"Q {q} below threshold {THRESHOLD}")
    ask = not reasons

    question, category = None, None
    if ask and opt is not None:
        category = (open_cats or hypotheses or ["other"])[0]
        question = phrase_question(case, event_type, opt, category, cheapest, earliest)
    elif ask:
        ask = False
        reasons.append("no visible trade-off to ask about")

    return {
        "q": q,
        "features": {"novelty": novelty, "decision_importance": importance,
                     "alternative_gap": gap, "knowledge_uncertainty": uncertainty},
        "hypotheses": hypotheses,
        "ask": ask,
        "question": question,
        "category": category,
        "is_guardrail": category in GUARDRAIL_CATEGORIES,
        "reasons": reasons or [f"Q {q} >= {THRESHOLD}: {', '.join(open_cats) or 'unexplained choice'}"],
    }


def phrase_question(case: Case, event_type: str, opt, category: str, cheapest: str, earliest: str) -> str:
    """One short question about the visible trade-off. Never asks what the screen already shows."""
    city = opt.hub_city
    perk = "the earliest arrival" if opt.id == earliest else ("the cheapest" if opt.id == cheapest else None)
    if event_type == "alternative_rejected":
        if category == "connection_risk":
            lead = f"You ruled out {city} even though it's {perk}." if perk else f"You ruled out {city}."
            return f"{lead} It has a {opt.connection_min}-minute connection with a checked bag. Is there a minimum you won't go below?"
        if category == "customer_deadline":
            lead = f"{city} was {perk}." if perk else f"You ruled out {city}."
            return f"{lead} What made it a no?"
        if category == "authority_boundary":
            return f"{city} is {opt.cabin.replace('_', ' ')} only. Could you have booked that yourself, or would someone need to approve it?"
        return f"You ruled out {city}. What made it a no?"
    if event_type == "escalation_requested":
        return (f"You stopped to ask before booking {opt.cabin.replace('_', ' ')} on {city}. "
                f"Where is your limit, and who has to approve it?")
    if event_type in ("alternative_selected", "rebook_confirmed"):
        if category == "authority_boundary":
            return (f"{city} is a cabin change from {case.passenger.original_cabin.replace('_', ' ')}. "
                    f"Is that yours to approve, or would you stop and ask someone?")
        if opt.id not in (cheapest, earliest):
            return f"You chose {city} even though it's neither the cheapest nor the earliest. What made it the better option?"
        return f"Why {city} over the others?"
    return f"What are you checking on {city}?"
