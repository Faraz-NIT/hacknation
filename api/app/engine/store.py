"""Rule persistence + provenance linking (event, transcript span, quote)."""
from __future__ import annotations

from typing import Any, Optional

from .. import db
from ..models import Case, LearnedRule
from .redact import redact
from .rules import refresh


def load_case(session_id: str) -> Case:
    return Case.model_validate(db.loads(db.session_row(session_id)["case_json"]))


def rules_for(session_id: str) -> list[LearnedRule]:
    rows = db.query("SELECT json FROM rules WHERE session_id=? ORDER BY rowid", (session_id,))
    return [LearnedRule.model_validate(db.loads(r["json"])) for r in rows]


def save_rule(rule: LearnedRule) -> LearnedRule:
    refresh(rule)
    exists = db.one("SELECT id FROM rules WHERE id=?", (rule.rule_id,))
    if exists:
        db.execute("UPDATE rules SET json=? WHERE id=?", (rule.model_dump_json(), rule.rule_id))
    else:
        db.execute("INSERT INTO rules (id, session_id, json) VALUES (?,?,?)",
                   (rule.rule_id, rule.session_id, rule.model_dump_json()))
    return rule


def get_rule(rule_id: str) -> LearnedRule:
    row = db.one("SELECT json FROM rules WHERE id=?", (rule_id,))
    if row is None:
        raise KeyError(rule_id)
    return LearnedRule.model_validate(db.loads(row["json"]))


def latest_question(session_id: str, phase: Optional[str] = None) -> Optional[dict[str, Any]]:
    sql = "SELECT * FROM questions WHERE session_id=? AND asked_ts IS NOT NULL"
    params: tuple = (session_id,)
    if phase:
        sql += " AND phase=?"
        params += (phase,)
    return db.one(sql + " ORDER BY asked_ts DESC LIMIT 1", params)


def answer_span(session_id: str, since_ts: Optional[float]) -> tuple[Optional[str], Optional[str]]:
    """Expert's on-record words since the question was asked -> (quote, 'mm:ss-mm:ss')."""
    if since_ts is None:
        return None, None
    rows = db.query(
        "SELECT ts, text FROM transcript WHERE session_id=? AND role='user' AND off_record=0 AND ts>=? ORDER BY ts",
        (session_id, since_ts),
    )
    if not rows:
        return None, None
    quote = " ".join(r["text"] for r in rows)[:400]
    return quote, f"{db.fmt_ts(rows[0]['ts'])}-{db.fmt_ts(rows[-1]['ts'])}"


def record(
    session_id: str,
    decision_type: str,
    reason: str,
    *,
    threshold: Optional[int] = None,
    escalation: Optional[str] = None,
    exception: Optional[str] = None,
    guardrail: Optional[str] = None,
    quote: Optional[str] = None,
    event_id: Optional[str] = None,
    confidence: float = 0.7,
    extracted_by: str = "agent",
) -> LearnedRule:
    """Create a rule, or merge into the session's existing rule of the same type."""
    case = load_case(session_id)
    q = latest_question(session_id)
    if event_id is None and q is not None:
        event_id = q["event_id"]
    if q is not None:
        db.execute("UPDATE questions SET answered=1 WHERE id=?", (q["id"],))
    span_quote, span = answer_span(session_id, q["asked_ts"] if q else None)
    quote = redact(quote or span_quote or reason, case)
    reason = redact(reason, case)
    ev = db.one("SELECT ts FROM events WHERE id=?", (event_id,)) if event_id else None

    existing = next((r for r in rules_for(session_id) if r.decision_type == decision_type and decision_type != "other"), None)
    if existing:
        existing.threshold_min = threshold or existing.threshold_min
        existing.escalation = escalation or existing.escalation
        existing.exception = exception or existing.exception
        if quote and not existing.quote:
            existing.quote = quote
        elif quote and quote != existing.quote and quote not in existing.notes:
            existing.notes.append(quote)
        existing.confidence = round(min(0.95, max(existing.confidence, confidence) + 0.05), 2)
        return save_rule(existing)

    rule = LearnedRule(
        rule_id=db.new_id("R"),
        session_id=session_id,
        decision_type=decision_type,  # type: ignore[arg-type]
        title="",
        condition={},
        action="note",
        reason=reason,
        guardrail=guardrail,
        threshold_min=threshold,
        escalation=escalation,
        exception=exception,
        source_event_id=event_id,
        source_ts=ev["ts"] if ev else db.session_ts(session_id),
        source_transcript_span=span,
        quote=quote,
        confidence=confidence,
        extracted_by=extracted_by,
    )
    return save_rule(rule)
