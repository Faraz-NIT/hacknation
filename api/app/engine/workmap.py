"""Session -> Work Map: ordered steps, each linked to a screen moment, the
decision, the reason in the expert's words and the guardrails around it."""
from __future__ import annotations

from typing import Any

from .. import db
from ..models import Case, LearnedRule
from .store import load_case, rules_for

TITLE = {
    "case_opened": "Review the disruption and the passenger's constraints",
    "alternative_rejected": "Rule out {label}",
    "alternative_selected": "Choose {label}",
    "escalation_requested": "Escalate {label} for approval",
    "rebook_confirmed": "Confirm rebooking {label}",
}


def _decision(case: Case, ev: dict[str, Any]) -> str:
    if ev["type"] == "case_opened":
        p = case.passenger
        return (f"Disrupted leg {case.flight.disrupted_leg} ({case.flight.status}). Constraints: "
                f"{'checked bag' if p.checked_bag else 'carry-on only'}, land by {p.arrival_deadline}, "
                f"{p.original_cabin.replace('_', ' ')} ticket.")
    opt = case.option(ev["option_id"])
    facts = f"{opt.hub_city}, arr {opt.arrival}, {opt.connection_min}-min connection, EUR {opt.price_eur}, {opt.cabin.replace('_', ' ')}"
    verb = {"alternative_rejected": "Rejected", "alternative_selected": "Selected",
            "escalation_requested": "Requested supervisor approval for", "rebook_confirmed": "Confirmed"}[ev["type"]]
    return f"{verb} {facts}"


def build(session_id: str) -> dict[str, Any]:
    case = load_case(session_id)
    sess = db.session_row(session_id)
    state = db.loads(sess["state_json"], {})
    rules = rules_for(session_id)
    events = db.query(
        "SELECT * FROM events WHERE session_id=? AND off_record=0 AND type IN "
        "('case_opened','alternative_rejected','alternative_selected','escalation_requested','rebook_confirmed') ORDER BY ts",
        (session_id,),
    )
    questions = db.query("SELECT * FROM questions WHERE session_id=? AND asked_ts IS NOT NULL ORDER BY asked_ts", (session_id,))
    steps: list[dict[str, Any]] = []
    placed: set[str] = set()

    for ev in events:
        score = db.loads(ev["score_json"], {})
        linked = [r for r in rules if r.source_event_id == ev["id"]]
        placed.update(r.rule_id for r in linked)
        label = case.option(ev["option_id"]).label if ev["option_id"] else ""
        steps.append({
            "event_id": ev["id"],
            "type": ev["type"],
            "title": TITLE[ev["type"]].format(label=label),
            "ts": ev["ts"],
            "ts_label": db.fmt_ts(ev["ts"]),
            "option_id": ev["option_id"],
            "decision": _decision(case, ev),
            "snapshot": db.loads(ev["snapshot_json"], {}),
            "question": next((q["text"] for q in questions if q["event_id"] == ev["id"]), None),
            "hypotheses": score.get("hypotheses", []),
            "rule_ids": [r.rule_id for r in linked],
        })

    # Rules learned in the debrief: attach to the step whose trade-off raised that category.
    for r in rules:
        if r.rule_id in placed:
            continue
        target = next((s for s in reversed(steps) if r.decision_type in s["hypotheses"]), None)
        if target is None:
            target = next((s for s in steps if s["type"] == "case_opened"), None)
        if target is not None:
            target["rule_ids"].append(r.rule_id)
            placed.add(r.rule_id)

    by_id = {r.rule_id: r for r in rules}
    for i, s in enumerate(steps, 1):
        rs: list[LearnedRule] = [by_id[x] for x in s["rule_ids"]]
        s["step_no"] = i
        s["judgment_call"] = bool(rs or s["question"])
        s["reasons"] = [{"rule_id": r.rule_id, "quote": r.quote, "span": r.source_transcript_span,
                         "ts_label": db.fmt_ts(r.source_ts), "notes": r.notes} for r in rs]
        s["guardrails"] = [{"rule_id": r.rule_id, "text": r.guardrail, "confirmed": r.expert_confirmed,
                            "decision_type": r.decision_type} for r in rs if r.guardrail]
        s["confidence"] = max((r.confidence for r in rs), default=None)
        s["confirmed"] = all(r.expert_confirmed for r in rs) if rs else None

    return {
        "session_id": session_id,
        "expert_name": state.get("expert_name", "Expert"),
        "case": {"case_id": case.case_id, "title": case.title, "route": case.flight.route},
        "steps": steps,
        "rules": [r.model_dump() for r in rules],
        "stats": {
            "steps": len(steps),
            "judgment_calls": sum(1 for s in steps if s["judgment_call"]),
            "guardrails": sum(1 for r in rules if r.guardrail),
            "confirmed_rules": sum(1 for r in rules if r.expert_confirmed),
            "live_questions": sum(1 for q in questions if q["phase"] == "live"),
            "debrief_questions": len(state.get("answered_gaps", [])),
            "corrections": int(state.get("corrections", 0)),
            "off_record_events": db.one("SELECT COUNT(*) n FROM events WHERE session_id=? AND off_record=1", (session_id,))["n"],
        },
        "teachback_confirmed": bool(state.get("teachback_confirmed")),
    }


def export_markdown(session_id: str) -> str:
    """Stretch goal: agent-ready guardrails an automation agent can load."""
    wm = build(session_id)
    lines = [f"# Disruption rebooking procedure (learned from {wm['expert_name']})", "",
             "Load these as hard constraints. Stop and hand over to a human where indicated.", "", "## Steps"]
    for s in wm["steps"]:
        lines.append(f"{s['step_no']}. {s['title']}")
    lines += ["", "## Guardrails (expert-confirmed only)"]
    for r in wm["rules"]:
        if r["expert_confirmed"] and r["guardrail"]:
            lines.append(f"- **{r['title']}**: {r['guardrail']}")
            lines.append(f"  - condition: `{r['condition']}` -> `{r['action']}`")
            if r.get("exception"):
                lines.append(f"  - exception: {r['exception']}")
            lines.append(f"  - expert's words ({r.get('source_transcript_span') or 'debrief'}): \"{r.get('quote')}\"")
    lines += ["", "## Stop and ask a human when", "- an option requires a cabin change, upgrade or waiver",
              "- no option satisfies every guardrail above"]
    return "\n".join(lines) + "\n"
