"""Formal reasoning over the learned guardrails with the Z3 SMT solver.

`rules.py` stays the enforcement path. This module mirrors its semantics as
Z3 formulas over the same decision facts, which lets us answer questions a
plain evaluator cannot:

- counterfactuals: the smallest change to an option that would make it pass
- analysis: dead rules, redundant (subsumed) rules, inconsistent rules with a
  concrete witness, and the "safe envelope" the rule set actually enforces
- equivalence: whether two rule sets block exactly the same situations
"""
from __future__ import annotations

import time
from typing import Any, Optional

import z3

from ..models import Case, LearnedRule
from .rules import enforceable, hhmm, option_facts

DAY = 24 * 60
BOOL_FACTS = ("checked_bag", "has_connection", "cabin_change", "has_supervisor_approval")
INT_FACTS = ("connection_min", "arrival_margin_min")


# ------------------------------------------------------------------ encoding
def fact_vars(prefix: str = "") -> dict[str, Any]:
    v: dict[str, Any] = {k: z3.Bool(prefix + k) for k in BOOL_FACTS}
    v.update({k: z3.Int(prefix + k) for k in INT_FACTS})
    return v


def domain(v: dict[str, Any]) -> z3.BoolRef:
    """Physically possible facts: a nonstop has no connection time."""
    return z3.And(
        v["connection_min"] >= 0, v["connection_min"] <= DAY,
        v["arrival_margin_min"] >= -DAY, v["arrival_margin_min"] <= DAY,
        z3.Implies(z3.Not(v["has_connection"]), v["connection_min"] == 0),
    )


def _cmp(actual: Any, spec: Any) -> z3.BoolRef:
    """Mirror of rules._cmp. A None reference never matches, as in Python."""
    if isinstance(spec, dict):
        parts = []
        for op, ref in spec.items():
            if ref is None:
                return z3.BoolVal(False)
            parts.append({"lt": actual < ref, "lte": actual <= ref, "gt": actual > ref,
                          "gte": actual >= ref, "eq": actual == ref}[op])
        return z3.And(*parts) if parts else z3.BoolVal(True)
    return actual == spec


def violation(rule: LearnedRule, v: dict[str, Any]) -> z3.BoolRef:
    """Mirror of rules.violates as a formula over the fact variables."""
    if not enforceable(rule) or not rule.condition:
        return z3.BoolVal(False)
    if any(key not in v for key in rule.condition):
        return z3.BoolVal(False)
    cond = z3.And(*[_cmp(v[k], spec) for k, spec in rule.condition.items()])
    if rule.action == "require_escalation":
        return z3.And(cond, z3.Not(v["has_supervisor_approval"]))
    if rule.action == "avoid_route":
        return cond
    return z3.BoolVal(False)


def blocked(rules: list[LearnedRule], v: dict[str, Any]) -> z3.BoolRef:
    return z3.Or(*[violation(r, v) for r in rules]) if rules else z3.BoolVal(False)


def _model_facts(m: z3.ModelRef, v: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in BOOL_FACTS:
        out[k] = z3.is_true(m.eval(v[k], model_completion=True))
    for k in INT_FACTS:
        out[k] = m.eval(v[k], model_completion=True).as_long()
    return out


def holds(formula: z3.BoolRef, facts: dict[str, Any], v: dict[str, Any]) -> bool:
    """Evaluate a formula on concrete facts (used to cross-check the encoding)."""
    subs = [(v[k], z3.BoolVal(bool(facts[k]))) for k in BOOL_FACTS]
    subs += [(v[k], z3.IntVal(int(facts[k]))) for k in INT_FACTS]
    return z3.is_true(z3.simplify(z3.substitute(formula, *subs)))


def describe(facts: dict[str, Any]) -> str:
    bits = ["checked bag" if facts["checked_bag"] else "carry-on only"]
    bits.append(f"{facts['connection_min']}-min connection" if facts["has_connection"] else "nonstop")
    m = facts["arrival_margin_min"]
    bits.append(f"lands {m} min before the deadline" if m >= 0 else f"lands {-m} min after the deadline")
    if facts["cabin_change"]:
        bits.append("cabin upgrade" + (" with approval" if facts["has_supervisor_approval"] else " without approval"))
    return ", ".join(bits)


# ------------------------------------------------------------ counterfactuals
def _hhmm(minutes: int) -> str:
    minutes %= DAY
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def counterfactuals(case: Case, option_id: str, rules: list[LearnedRule], has_supervisor_approval: bool = False,
                    limit: int = 3) -> list[dict[str, Any]]:
    """Smallest changes that would make an option pass, one per distinct strategy.

    Levers: connection time, arrival time, checked bag, supervisor approval.
    Lexicographic objective: fewest levers changed, then smallest change in
    minutes. Each next answer must use a different set of levers, so the list
    reads as alternatives ("...or carry-on only, or land by 09:40").
    """
    opt = case.option(option_id)
    f0 = option_facts(case, opt, has_supervisor_approval)
    v = fact_vars("cf_")
    changed = {
        "connection_min": v["connection_min"] != f0["connection_min"],
        "arrival_margin_min": v["arrival_margin_min"] != f0["arrival_margin_min"],
        "checked_bag": v["checked_bag"] != f0["checked_bag"],
        "has_supervisor_approval": v["has_supervisor_approval"] != f0["has_supervisor_approval"],
    }
    base = [
        domain(v), z3.Not(blocked(rules, v)),
        v["has_connection"] == f0["has_connection"], v["cabin_change"] == f0["cabin_change"],
        v["has_supervisor_approval"] if f0["has_supervisor_approval"] else z3.BoolVal(True),
    ]
    if not f0["has_connection"]:
        base.append(z3.Not(changed["connection_min"]))
    n_changed = z3.Sum(*[z3.If(c, 1, 0) for c in changed.values()])
    dist = (z3.If(v["connection_min"] >= f0["connection_min"], v["connection_min"] - f0["connection_min"],
                  f0["connection_min"] - v["connection_min"])
            + z3.If(v["arrival_margin_min"] >= f0["arrival_margin_min"], v["arrival_margin_min"] - f0["arrival_margin_min"],
                    f0["arrival_margin_min"] - v["arrival_margin_min"])
            # Facts the agent can't choose (the passenger's bag, someone else's approval) rank after schedule changes.
            + z3.If(changed["checked_bag"], 60, 0) + z3.If(changed["has_supervisor_approval"], 30, 0))

    deadline = hhmm(case.passenger.arrival_deadline)
    escalation = next((r.escalation for r in rules if r.decision_type == "authority_boundary" and r.escalation), None)
    out: list[dict[str, Any]] = []
    exclusions: list[z3.BoolRef] = []
    for _ in range(limit):
        o = z3.Optimize()
        o.add(*base, *exclusions)
        o.minimize(n_changed)
        o.minimize(dist)
        if o.check() != z3.sat:
            break
        facts = _model_facts(o.model(), v)
        levers = [k for k in changed if facts[k] != f0[k]]
        if not levers:  # already allowed
            return []
        changes: dict[str, Any] = {}
        text: list[str] = []
        for k in levers:
            if k == "connection_min":
                changes[k] = facts[k]
                text.append(f"the connection were at least {facts[k]} min" if facts[k] > f0[k]
                            else f"the connection were at most {facts[k]} min")
            elif k == "arrival_margin_min":
                changes["arrival"] = _hhmm(deadline - facts[k])
                text.append(f"it landed by {changes['arrival']}" if facts[k] > f0[k]
                            else f"it landed no earlier than {changes['arrival']}")
            elif k == "checked_bag":
                changes[k] = facts[k]
                text.append("the passenger had carry-on only" if not facts[k] else "the passenger had a checked bag")
            elif k == "has_supervisor_approval":
                changes[k] = facts[k]
                text.append(f"{escalation or 'a supervisor'} approved it")
        out.append({"changes": changes, "levers": levers, "text": f"Allowed if {' and '.join(text)}."})
        exclusions.append(z3.Or(*[z3.Not(changed[k]) for k in levers]))
    return out


# ------------------------------------------------------------------ analysis
def _sat(*formulas: z3.BoolRef, v: Optional[dict[str, Any]] = None):
    s = z3.Solver()
    s.add(*formulas)
    if s.check() == z3.sat:
        return _model_facts(s.model(), v) if v is not None else True
    return None


def _benign(v: dict[str, Any]) -> list[z3.BoolRef]:
    """Hold every other risk factor at its safest value when probing one."""
    return [z3.Not(v["cabin_change"]), v["arrival_margin_min"] >= 120]


def envelope(rules: list[LearnedRule]) -> dict[str, Any]:
    """What the rule set actually enforces, as extreme allowed situations."""
    v = fact_vars("env_")
    allowed = [domain(v), z3.Not(blocked(rules, v))]
    out: dict[str, Any] = {}

    o = z3.Optimize()
    o.add(*allowed, v["checked_bag"], v["has_connection"], *_benign(v))
    h = o.minimize(v["connection_min"])
    shortest = o.lower(h).as_long() if o.check() == z3.sat else None
    out["shortest_connection_with_bag"] = shortest
    out["connection_guarded"] = bool(shortest and shortest > 0)

    o = z3.Optimize()
    o.add(*allowed, z3.Not(v["cabin_change"]), z3.Not(v["has_connection"]))
    h = o.minimize(v["arrival_margin_min"])
    latest = o.lower(h).as_long() if o.check() == z3.sat else None
    out["min_arrival_margin"] = latest
    out["deadline_guarded"] = latest is not None and latest > -DAY

    out["upgrade_without_approval_allowed"] = _sat(
        *allowed, v["cabin_change"], z3.Not(v["has_supervisor_approval"]), z3.Not(v["has_connection"]),
        v["arrival_margin_min"] >= 120) is not None
    return out


def analyze(rules: list[LearnedRule]) -> dict[str, Any]:
    t0 = time.perf_counter()
    v = fact_vars("an_")
    active = [r for r in rules if enforceable(r)]
    findings: list[dict[str, Any]] = []

    for r in active:
        if _sat(domain(v), violation(r, v)) is None:
            findings.append({"kind": "dead", "rule_ids": [r.rule_id],
                             "text": f"\"{r.title}\" can never fire on a realistic booking."})

    reported: set[frozenset[str]] = set()
    for a in active:
        for b in active:
            if a.rule_id == b.rule_id or frozenset((a.rule_id, b.rule_id)) in reported:
                continue
            if a.decision_type == b.decision_type and (a.threshold_min != b.threshold_min or a.escalation != b.escalation):
                w = _sat(domain(v), violation(a, v) != violation(b, v), v=v)
                if w:
                    blocker, other = (a, b) if holds(violation(a, v), w, v) else (b, a)
                    findings.append({"kind": "inconsistent", "rule_ids": [a.rule_id, b.rule_id], "witness": w,
                                     "text": f"Two \"{a.title}\" rules disagree: on a booking with {describe(w)}, "
                                             f"{blocker.rule_id} blocks but {other.rule_id} allows."})
                    reported.add(frozenset((a.rule_id, b.rule_id)))
                    continue
            if _sat(domain(v), violation(b, v), z3.Not(violation(a, v))) is None:
                same = _sat(domain(v), violation(a, v), z3.Not(violation(b, v))) is None
                findings.append({"kind": "duplicate" if same else "subsumed", "rule_ids": [b.rule_id, a.rule_id],
                                 "text": (f"{b.rule_id} and {a.rule_id} block exactly the same bookings." if same else
                                          f"{b.rule_id} is redundant: {a.rule_id} already blocks everything it blocks.")})
                reported.add(frozenset((a.rule_id, b.rule_id)))

    env = envelope([r for r in active if r.expert_confirmed] or active)
    if not env["connection_guarded"]:
        findings.append({"kind": "unguarded", "rule_ids": [], "text": "Nothing stops a very short connection with a checked bag."})
    if not env["deadline_guarded"]:
        findings.append({"kind": "unguarded", "rule_ids": [], "text": "Nothing stops an arrival after the passenger's deadline."})
    if env["upgrade_without_approval_allowed"]:
        findings.append({"kind": "unguarded", "rule_ids": [], "text": "A cabin upgrade can be booked without anyone's approval."})

    return {"rules_checked": len(active), "findings": findings, "envelope": env,
            "consistent": not any(f["kind"] in ("inconsistent", "dead") for f in findings),
            "solver_ms": round((time.perf_counter() - t0) * 1000, 1), "solver": f"Z3 {z3.get_version_string()}"}


def equivalent(a: list[LearnedRule], b: list[LearnedRule]) -> tuple[bool, Optional[dict[str, Any]]]:
    """Do two rule sets block exactly the same bookings? Returns a witness if not."""
    v = fact_vars("eq_")
    w = _sat(domain(v), blocked(a, v) != blocked(b, v), v=v)
    return w is None, w
