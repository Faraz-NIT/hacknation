"""Z3 verifier: the encoding must agree with the Python evaluator, and the
analyses must find what we plant."""
import random

from app.engine import verify
from app.engine.rules import refresh, violates
from app.models import Case, LearnedRule
from app.services.cases import load_fixture


def rule(rid, kind, threshold=None, escalation=None, confirmed=True):
    r = LearnedRule(rule_id=rid, session_id="S", decision_type=kind, title="", condition={}, action="note",
                    reason="test", threshold_min=threshold, escalation=escalation, expert_confirmed=confirmed)
    return refresh(r)


RULES = [rule("R1", "connection_risk", 80), rule("R2", "customer_deadline", 15),
         rule("R3", "authority_boundary", escalation="duty manager")]


def random_facts(rng):
    has_conn = rng.random() < 0.8
    return {"checked_bag": rng.random() < 0.5, "has_connection": has_conn,
            "connection_min": rng.randint(1, 200) if has_conn else 0,
            "arrival_margin_min": rng.randint(-180, 240), "cabin_change": rng.random() < 0.3,
            "has_supervisor_approval": rng.random() < 0.3}


def test_encoding_matches_python_evaluator():
    rng = random.Random(7)
    v = verify.fact_vars()
    for _ in range(2000):
        f = random_facts(rng)
        for r in RULES:
            assert verify.holds(verify.violation(r, v), f, v) == violates(r, f), (r.rule_id, f)


def test_counterfactuals_case_b_option_a():
    case: Case = load_fixture("case_B")  # A: 48-min connection, checked bag
    cfs = verify.counterfactuals(case, "A", RULES)
    levers = [tuple(c["levers"]) for c in cfs]
    assert ("connection_min",) in levers and ("checked_bag",) in levers
    conn = next(c for c in cfs if c["levers"] == ["connection_min"])
    assert conn["changes"]["connection_min"] == 80  # exactly the expert's floor
    assert verify.counterfactuals(case, "B", RULES) == []  # already allowed
    up = verify.counterfactuals(case, "D", RULES)  # premium economy: needs approval
    assert up[0]["levers"] == ["has_supervisor_approval"] and "duty manager" in up[0]["text"]


def test_analysis_finds_planted_problems():
    clean = verify.analyze(RULES)
    assert clean["consistent"] and not clean["findings"]
    assert clean["envelope"]["shortest_connection_with_bag"] == 80
    assert clean["envelope"]["min_arrival_margin"] == 15

    messy = verify.analyze(RULES + [rule("R4", "connection_risk", 60), rule("R5", "customer_deadline", -2000)])
    kinds = {f["kind"] for f in messy["findings"]}
    assert "inconsistent" in kinds and "dead" in kinds and not messy["consistent"]
    w = next(f for f in messy["findings"] if f["kind"] == "inconsistent")["witness"]
    assert w["checked_bag"] and 60 <= w["connection_min"] < 80

    gaps = verify.analyze([RULES[0]])
    assert sum(f["kind"] == "unguarded" for f in gaps["findings"]) == 2


def test_equivalence():
    same, _ = verify.equivalent(RULES, [RULES[2], RULES[0], RULES[1]])
    assert same
    diff, w = verify.equivalent(RULES, [rule("X1", "connection_risk", 75)] + RULES[1:])
    assert not diff and 75 <= w["connection_min"] < 80 and w["checked_bag"]
