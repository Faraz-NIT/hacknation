"""Decision facts, rule construction and the deterministic guardrail evaluator.

The LLM/agent never decides whether an action is allowed. It only proposes a
typed rule; enforcement below is plain Python over explicit facts.
"""
from __future__ import annotations

from typing import Any, Optional

from ..models import CABIN_RANK, Alternative, Case, LearnedRule

TITLES = {
    "connection_risk": "Minimum connection with a checked bag",
    "customer_deadline": "Protect the customer's arrival deadline",
    "authority_boundary": "Cabin change needs supervisor approval",
    "other": "Expert note",
}


def hhmm(value: str) -> int:
    h, m = value.split(":")
    return int(h) * 60 + int(m)


def option_facts(case: Case, opt: Alternative, has_supervisor_approval: bool = False) -> dict[str, Any]:
    margin = hhmm(case.passenger.arrival_deadline) - hhmm(opt.arrival)
    return {
        "option_id": opt.id,
        "checked_bag": case.passenger.checked_bag,
        "has_connection": opt.hub not in ("-", "", None),
        "connection_min": opt.connection_min,
        "arrival_margin_min": margin,
        "arrival_after_deadline": margin < 0,
        "cabin_change": CABIN_RANK.get(opt.cabin, 0) > CABIN_RANK.get(case.passenger.original_cabin, 0),
        "has_supervisor_approval": has_supervisor_approval,
        "price_eur": opt.price_eur,
    }


# ---------------------------------------------------------------- construction
def build_condition(decision_type: str, threshold: Optional[int]) -> dict[str, Any]:
    if decision_type == "connection_risk":
        return {"checked_bag": True, "has_connection": True, "connection_min": {"lt": threshold}}
    if decision_type == "customer_deadline":
        return {"arrival_margin_min": {"lt": threshold if threshold is not None else 0}}
    if decision_type == "authority_boundary":
        return {"cabin_change": True}
    return {}


def guardrail_text(rule: LearnedRule) -> Optional[str]:
    t = rule.threshold_min
    if rule.decision_type == "connection_risk":
        floor = f"{t} min" if t else "the expert's minimum (not yet stated)"
        return f"With a checked bag, never book a connection shorter than {floor}."
    if rule.decision_type == "customer_deadline":
        if t:
            return f"Never land after the customer's deadline; keep at least {t} min margin."
        return "Never land after the customer's deadline."
    if rule.decision_type == "authority_boundary":
        who = rule.escalation or "a supervisor (who exactly is not yet stated)"
        return f"Any cabin upgrade or waiver: stop and get approval from {who} before ticketing."
    return rule.guardrail


def refresh(rule: LearnedRule) -> LearnedRule:
    """Re-derive machine fields after the expert adds or corrects details."""
    rule.condition = build_condition(rule.decision_type, rule.threshold_min)
    rule.action = {
        "connection_risk": "avoid_route",
        "customer_deadline": "avoid_route",
        "authority_boundary": "require_escalation",
    }.get(rule.decision_type, "note")
    rule.title = TITLES[rule.decision_type]
    rule.guardrail = guardrail_text(rule)
    return rule


def enforceable(rule: LearnedRule) -> bool:
    if rule.action == "note":
        return False
    if rule.decision_type == "connection_risk" and not rule.threshold_min:
        return False
    return True


# ------------------------------------------------------------------ evaluation
def _cmp(actual: Any, spec: Any) -> bool:
    if isinstance(spec, dict):
        for op, ref in spec.items():
            if ref is None or actual is None:
                return False
            if op == "lt" and not actual < ref:
                return False
            if op == "lte" and not actual <= ref:
                return False
            if op == "gt" and not actual > ref:
                return False
            if op == "gte" and not actual >= ref:
                return False
            if op == "eq" and actual != ref:
                return False
        return True
    return actual == spec


def matches(condition: dict[str, Any], facts: dict[str, Any]) -> bool:
    if not condition:
        return False
    return all(_cmp(facts.get(key), spec) for key, spec in condition.items())


def violates(rule: LearnedRule, facts: dict[str, Any]) -> bool:
    if not enforceable(rule) or not matches(rule.condition, facts):
        return False
    if rule.action == "require_escalation":
        return not facts.get("has_supervisor_approval", False)
    return rule.action == "avoid_route"


def evaluate(case: Case, option_id: str, rules: list[LearnedRule], has_supervisor_approval: bool = False):
    """Return (blocking_violations, draft_warnings, facts). Deterministic only."""
    opt = case.option(option_id)
    facts = option_facts(case, opt, has_supervisor_approval)
    violations, warnings = [], []
    for rule in rules:
        if violates(rule, facts):
            (violations if rule.expert_confirmed else warnings).append(rule)
    return violations, warnings, facts


def explain_facts(rule: LearnedRule, case: Case, facts: dict[str, Any]) -> str:
    opt = case.option(facts["option_id"])
    name = f"Option {opt.id} ({opt.label})"
    if rule.decision_type == "connection_risk":
        return (f"{name} has a {opt.connection_min}-minute connection in {opt.hub_city} "
                f"and the passenger has a checked bag (floor: {rule.threshold_min} min).")
    if rule.decision_type == "customer_deadline":
        m = facts["arrival_margin_min"]
        when = f"{-m} min after" if m < 0 else f"only {m} min before"
        return f"{name} lands at {opt.arrival}, {when} the {case.passenger.arrival_deadline} deadline."
    if rule.decision_type == "authority_boundary":
        return (f"{name} is {opt.cabin.replace('_', ' ')} but the ticket is "
                f"{case.passenger.original_cabin.replace('_', ' ')}: that is a cabin change.")
    return rule.reason


def risk_flags(case: Case, opt: Alternative) -> list[str]:
    """Visible-fact risk profile, used by the question scorer (not enforcement)."""
    f = option_facts(case, opt)
    flags = []
    if f["checked_bag"] and f["has_connection"] and f["connection_min"] < 75:
        flags.append("short_connection_with_bag")
    if f["arrival_after_deadline"]:
        flags.append("after_deadline")
    if f["cabin_change"]:
        flags.append("cabin_change")
    return flags
