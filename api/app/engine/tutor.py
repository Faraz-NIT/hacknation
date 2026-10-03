"""Teach mode: interventions in the expert's words, and the mastery report."""
from __future__ import annotations

from typing import Any, Optional

from .. import db
from ..models import Case, LearnedRule
from .extraction import classify
from .rules import explain_facts, option_facts, violates


def screen_moment(rule: LearnedRule) -> Optional[dict[str, Any]]:
    if not rule.source_event_id:
        return None
    ev = db.one("SELECT * FROM events WHERE id=?", (rule.source_event_id,))
    if not ev:
        return None
    return {"event_id": ev["id"], "type": ev["type"], "option_id": ev["option_id"], "ts": ev["ts"],
            "ts_label": db.fmt_ts(ev["ts"]), "snapshot": db.loads(ev["snapshot_json"], {})}


def intervention(case: Case, rule: LearnedRule, facts: dict[str, Any], expert_name: str) -> dict[str, Any]:
    why = explain_facts(rule, case, facts)
    quote = rule.quote or rule.reason
    return {
        "rule_id": rule.rule_id,
        "decision_type": rule.decision_type,
        "title": rule.title,
        "guardrail": rule.guardrail,
        "why": why,
        "expert_quote": quote,
        "expert_span": rule.source_transcript_span,
        "screen_moment": screen_moment(rule),
        "tutor_script": f"{expert_name} would stop here. {why} Why do you think that's a problem?",
        "reveal_script": f"Here's how {expert_name} put it: \"{quote}\"",
        "confirmed": rule.expert_confirmed,
    }


def applicable_rules(case: Case, rules: list[LearnedRule]) -> list[LearnedRule]:
    out = []
    for r in rules:
        if not r.expert_confirmed:
            continue
        if any(violates(r, option_facts(case, alt)) for alt in case.alternatives):
            out.append(r)
    return out


def judge_answer(text: str, rule: LearnedRule) -> bool:
    return classify(text).get(rule.decision_type, 0) > 0


def match_prediction(text: str, case: Case, rules: list[LearnedRule]) -> list[str]:
    low = text.lower()
    hits = []
    for r in rules:
        risky = [alt for alt in case.alternatives if violates(r, option_facts(case, alt))]
        named = any(alt.hub_city.lower() in low or alt.hub.lower() in low.split() for alt in risky)
        if classify(text).get(r.decision_type, 0) > 0 or named:
            hits.append(r.rule_id)
    return hits


def mastery(case: Case, rules: list[LearnedRule], session_id: str) -> dict[str, Any]:
    state = db.get_state(session_id)
    blocks = [db.loads(x["json"]) for x in db.query("SELECT json FROM interventions WHERE session_id=?", (session_id,))]
    blocked_rules = {rid for b in blocks if b.get("kind") == "block" for rid in b.get("rule_ids", [])}
    predicted = {rid for p in state.get("predictions", []) for rid in p.get("matched_rules", [])}
    explained = {e["rule_id"] for e in state.get("explanations", []) if e.get("correct")}
    final = state.get("final")
    items = []
    for r in applicable_rules(case, rules):
        violated = r.rule_id in blocked_rules
        final_ok = bool(final and final.get("clean"))
        if not final:
            st, label = "in_progress", "Case not finished"
        elif final_ok and not violated:
            st, label = "mastered", "Mastered: avoided without help"
        elif final_ok and violated and r.rule_id in explained:
            st, label = "coached", "Learned with coaching: blocked, explained, corrected"
        elif final_ok and violated:
            st, label = "practice", "Practice next: corrected, but couldn't explain why"
        else:
            st, label = "practice", "Practice next"
        items.append({"rule_id": r.rule_id, "title": r.title, "guardrail": r.guardrail, "status": st,
                      "label": label, "violated": violated, "predicted": r.rule_id in predicted,
                      "explained": r.rule_id in explained})
    practice = [i["title"] for i in items if i["status"] in ("practice", "coached")]
    return {
        "finished": bool(final),
        "final_option": final.get("option_id") if final else None,
        "interventions": len([b for b in blocks if b.get("kind") == "block"]),
        "items": items,
        "mastered": [i["title"] for i in items if i["status"] == "mastered"],
        "practice_next": practice,
        "summary": (f"Mastered {sum(i['status'] == 'mastered' for i in items)} of {len(items)} guardrails; "
                    f"{len(practice)} to practise next." if final else "In progress"),
    }
