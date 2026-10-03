"""SkyMentor Live API.

Run:  uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

from . import db
from .engine import debrief as debrief_engine
from .engine import extraction, scoring, tutor, workmap
from .engine.redact import redact
from .engine.rules import evaluate, refresh
from .engine.store import get_rule, load_case, record, rules_for, save_rule
from .models import (
    ActionIn, ConfirmIn, EventIn, ExtractIn, GapAnswerIn, RuleCorrectionIn,
    RuleRecordIn, SessionCreate, TraineeAnswerIn, TranscriptIn,
)
from .services import cases, live


def _load_dotenv() -> None:
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


_load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("skymentor")

app = FastAPI(title="SkyMentor Live API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def timing(request: Request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        log.info("%s %s %s %.0fms", request.method, request.url.path, response.status_code, (time.perf_counter() - t0) * 1000)
    return response


@app.exception_handler(KeyError)
async def not_found(_: Request, exc: KeyError):
    return JSONResponse(status_code=404, content={"detail": f"not found: {exc}"})


def _session(session_id: str) -> dict[str, Any]:
    return db.session_row(session_id)


def _public_case(session_id: str) -> dict[str, Any]:
    return db.loads(_session(session_id)["case_json"])


# ------------------------------------------------------------------- system
@app.get("/api/health")
def health():
    return {
        "ok": True,
        "integrations": {
            "elevenlabs": bool(os.environ.get("ELEVENLABS_API_KEY") and _agent_id("expert")) or bool(_agent_id("expert")),
            "elevenlabs_signed": bool(os.environ.get("ELEVENLABS_API_KEY")),
            "cerebras_extraction": bool(os.environ.get("CEREBRAS_API_KEY")),
            "aviationstack": bool(os.environ.get("AVIATIONSTACK_KEY")),
            "brightdata": bool(os.environ.get("BRIGHTDATA_API_TOKEN") and os.environ.get("BRIGHTDATA_FLIGHTS_DATASET_ID")),
            "open_meteo": os.environ.get("SKYMENTOR_OFFLINE") != "1",
        },
        "offline": os.environ.get("SKYMENTOR_OFFLINE") == "1",
    }


@app.post("/api/reset")
def reset():
    db.reset()
    return {"ok": True}


@app.post("/api/cache/warm")
def warm_cache():
    """Pre-fetch live data for both cases so the demo can run from cache later."""
    out = {}
    for cid in ("case_A", "case_B"):
        c = cases.build_case(cid, use_live=True)
        out[cid] = c.provenance
    return out


# ----------------------------------------------------------------- sessions
@app.post("/api/sessions")
def create_session(body: SessionCreate):
    case_id = body.case_id or cases.CASE_FOR_MODE[body.mode]
    case = cases.build_case(case_id, use_live=body.live)
    sid = db.new_id("S" if body.mode == "expert" else "T")
    state: dict[str, Any] = {"expert_name": body.expert_name, "answered_gaps": [], "corrections": 0}
    expert_sid = None
    if body.mode == "trainee":
        expert_sid = body.expert_session_id or _latest_expert()
        if expert_sid:
            state["expert_name"] = db.get_state(expert_sid).get("expert_name", body.expert_name)
        state.update({"predictions": [], "explanations": []})
    db.execute(
        "INSERT INTO sessions (id, mode, created, case_json, expert_session_id, state_json) VALUES (?,?,?,?,?,?)",
        (sid, body.mode, time.time(), case.model_dump_json(), expert_sid, db.dumps(state)),
    )
    return {"session_id": sid, "mode": body.mode, "expert_session_id": expert_sid, "state": state,
            "case": case.model_dump()}


def _latest_expert() -> Optional[str]:
    rows = db.query("SELECT id FROM sessions WHERE mode='expert' ORDER BY created DESC")
    for r in rows:  # prefer the newest expert session with confirmed rules
        if any(x.expert_confirmed for x in rules_for(r["id"])):
            return r["id"]
    return rows[0]["id"] if rows else None


@app.get("/api/sessions/latest")
def latest_session(mode: str = "expert"):
    sid = _latest_expert() if mode == "expert" else None
    if sid is None:
        row = db.one("SELECT id FROM sessions WHERE mode=? ORDER BY created DESC LIMIT 1", (mode,))
        sid = row["id"] if row else None
    if sid is None:
        raise HTTPException(404, "no session yet")
    return get_session(sid)


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    s = _session(session_id)
    return {"session_id": s["id"], "mode": s["mode"], "expert_session_id": s["expert_session_id"],
            "state": db.loads(s["state_json"], {}), "case": db.loads(s["case_json"]),
            "clock": db.session_ts(session_id)}


class OffRecordIn(BaseModel):
    on: bool


@app.post("/api/sessions/{session_id}/off_record")
def set_off_record(session_id: str, body: OffRecordIn):
    state = db.get_state(session_id)
    state["off_record"] = body.on
    spans = state.setdefault("off_record_spans", [])
    now = db.session_ts(session_id)
    if body.on:
        spans.append([now, None])
    elif spans and spans[-1][1] is None:
        spans[-1][1] = now
    db.set_state(session_id, state)
    return {"off_record": body.on, "ts": now}


@app.get("/api/sessions/{session_id}/context")
def agent_context(session_id: str):
    """Compact, PII-free case context for the voice agent."""
    case = load_case(session_id)
    s = _session(session_id)
    p = case.passenger
    opts = "; ".join(
        f"{a.id}) {a.label} [{a.carrier}] arr {a.arrival}, connection {a.connection_min} min, EUR {a.price_eur}, {a.cabin}"
        + (f" ({a.note})" if a.note else "")
        for a in case.alternatives
    )
    wx = ", ".join(f"{k}: {v.get('risk')} wind {v.get('wind_kph')} km/h" for k, v in case.weather.items())
    text = (f"CASE {case.case_id}: {case.briefing} Disrupted leg {case.flight.disrupted_leg} ({case.flight.status}). "
            f"Passenger (name withheld): {'checked bag' if p.checked_bag else 'carry-on only'}, must land by "
            f"{p.arrival_deadline} ({redact(p.deadline_reason, case)}), ticketed {p.original_cabin}. Options: {opts}."
            + (f" Weather: {wx}." if wx else ""))
    out: dict[str, Any] = {"text": text, "mode": s["mode"]}
    if s["mode"] == "trainee" and s["expert_session_id"]:
        rules = [r for r in rules_for(s["expert_session_id"]) if r.expert_confirmed]
        out["expert_name"] = db.get_state(session_id).get("expert_name")
        out["rules_text"] = " ".join(f"[{r.rule_id}] {r.guardrail} (expert: \"{r.quote}\")" for r in rules)
    return out


# -------------------------------------------------------------------- cases
@app.get("/api/cases/{case_id}")
def get_case(case_id: str, live_data: bool = False):
    return cases.build_case(case_id, use_live=live_data).model_dump()


# ------------------------------------------------------------------- events
@app.post("/api/events")
def post_event(body: EventIn):
    s = _session(body.session_id)
    state = db.loads(s["state_json"], {})
    off = body.off_record or bool(state.get("off_record"))
    case = load_case(body.session_id)
    eid = db.new_id("evt")
    ts = db.session_ts(body.session_id)
    score: dict[str, Any] = {}
    question = None
    if s["mode"] == "expert" and body.type != "case_opened":
        asked = db.query("SELECT category, phase FROM questions WHERE session_id=? AND asked_ts IS NOT NULL", (body.session_id,))
        score = scoring.score_event(case, body.type, body.option_id, rules_for(body.session_id), asked, off)
        if score["ask"]:
            # Newer high-value question supersedes an unspoken pending one.
            db.execute("DELETE FROM questions WHERE session_id=? AND asked_ts IS NULL", (body.session_id,))
            qid = db.new_id("Q")
            db.execute(
                "INSERT INTO questions (id, session_id, event_id, created_ts, text, category, is_guardrail, phase) VALUES (?,?,?,?,?,?,?,?)",
                (qid, body.session_id, eid, ts, score["question"], score["category"], int(score["is_guardrail"]), "live"),
            )
            question = {"id": qid, "text": score["question"], "category": score["category"],
                        "is_guardrail": score["is_guardrail"], "event_id": eid}
    db.execute(
        "INSERT INTO events (id, session_id, ts, type, option_id, detail_json, snapshot_json, off_record, score_json) VALUES (?,?,?,?,?,?,?,?,?)",
        (eid, body.session_id, ts, body.type, body.option_id, db.dumps(body.detail),
         db.dumps(body.snapshot), int(off), db.dumps(score)),
    )
    log.info("event %s %s %s q=%s ask=%s", body.session_id, body.type, body.option_id, score.get("q"), score.get("ask"))
    return {"event_id": eid, "ts": ts, "ts_label": db.fmt_ts(ts), "off_record": off, "score": score, "question": question}


@app.get("/api/events/{session_id}")
def list_events(session_id: str):
    rows = db.query("SELECT * FROM events WHERE session_id=? ORDER BY ts", (session_id,))
    return [{**r, "detail": db.loads(r.pop("detail_json"), {}), "snapshot": db.loads(r.pop("snapshot_json"), {}),
             "score": db.loads(r.pop("score_json"), {}), "ts_label": db.fmt_ts(r["ts"])} for r in rows]


# ---------------------------------------------------------------- questions
@app.post("/api/questions/{question_id}/asked")
def question_asked(question_id: str):
    q = db.one("SELECT * FROM questions WHERE id=?", (question_id,))
    if not q:
        raise HTTPException(404, "question superseded or unknown")
    ts = db.session_ts(q["session_id"])
    db.execute("UPDATE questions SET asked_ts=? WHERE id=?", (ts, question_id))
    return {"question_id": question_id, "asked_ts": ts, "ts_label": db.fmt_ts(ts)}


class AskedIn(BaseModel):
    session_id: str
    text: str
    phase: str = "debrief"
    category: str = "debrief"
    gap_id: Optional[str] = None


@app.post("/api/questions")
def log_question(body: AskedIn):
    qid = db.new_id("Q")
    ts = db.session_ts(body.session_id)
    db.execute(
        "INSERT INTO questions (id, session_id, event_id, created_ts, asked_ts, text, category, is_guardrail, phase) VALUES (?,?,?,?,?,?,?,?,?)",
        (qid, body.session_id, None, ts, ts, body.text, body.category, 0, body.phase),
    )
    return {"question_id": qid, "asked_ts": ts}


@app.get("/api/questions/{session_id}")
def list_questions(session_id: str):
    rows = db.query("SELECT * FROM questions WHERE session_id=? AND asked_ts IS NOT NULL ORDER BY asked_ts", (session_id,))
    return [{**r, "ts_label": db.fmt_ts(r["asked_ts"])} for r in rows]


# --------------------------------------------------------------- transcript
@app.post("/api/transcript")
def post_transcript(body: TranscriptIn):
    case = load_case(body.session_id)
    state = db.get_state(body.session_id)
    off = body.off_record or bool(state.get("off_record"))
    clean = redact(body.text, case)
    ts = db.session_ts(body.session_id)
    db.execute("INSERT INTO transcript (id, session_id, ts, role, text, off_record) VALUES (?,?,?,?,?,?)",
               (db.new_id("tx"), body.session_id, ts, body.role, clean if not off else "[off the record]", int(off)))
    return {"ts": ts, "ts_label": db.fmt_ts(ts), "text": clean, "off_record": off, "redacted": clean != body.text}


@app.get("/api/transcript/{session_id}")
def get_transcript(session_id: str):
    rows = db.query("SELECT ts, role, text, off_record FROM transcript WHERE session_id=? ORDER BY ts", (session_id,))
    return [{**r, "ts_label": db.fmt_ts(r["ts"])} for r in rows]


# -------------------------------------------------------------------- rules
def _guard_off_record(session_id: str) -> None:
    if db.get_state(session_id).get("off_record"):
        raise HTTPException(409, "Expert is off the record; nothing is stored.")


@app.post("/api/rules/record")
def record_rule(body: RuleRecordIn):
    """Target of the agent's `record_expert_rule` client tool."""
    _guard_off_record(body.session_id)
    rule = record(
        body.session_id, body.decision_type, body.reason,
        threshold=body.threshold_minutes, escalation=body.escalation, exception=body.exception,
        guardrail=body.guardrail, quote=body.quote, event_id=body.event_id,
        confidence=body.confidence, extracted_by="agent",
    )
    return rule.model_dump()


@app.post("/api/rules/extract")
def extract_rules(body: ExtractIn):
    _guard_off_record(body.session_id)
    case = load_case(body.session_id)
    proposals = extraction.extract(redact(body.text, case), context=case.briefing)
    out = []
    for p in proposals:
        if p.decision_type == "other":
            continue
        out.append(record(
            body.session_id, p.decision_type, p.reason, threshold=p.threshold_minutes,
            escalation=p.escalation, exception=p.exception, quote=body.text, event_id=body.event_id,
            confidence=p.confidence, extracted_by=p.extracted_by,
        ).model_dump())
    if not out:  # still mark the question answered so it is not re-asked
        q = db.one("SELECT id FROM questions WHERE session_id=? AND asked_ts IS NOT NULL ORDER BY asked_ts DESC LIMIT 1", (body.session_id,))
        if q:
            db.execute("UPDATE questions SET answered=1 WHERE id=?", (q["id"],))
    return {"rules": out, "unresolved": not out}


@app.get("/api/rules/{session_id}")
def list_rules(session_id: str):
    return [r.model_dump() for r in rules_for(session_id)]


@app.post("/api/rules/correct")
def correct_rule(body: RuleCorrectionIn):
    session_rules = rules_for(body.session_id)
    if body.text and not body.rule_id:
        # Free-text correction ("no, it's 90 minutes at Heathrow"): parse it, then
        # apply only the fields the expert actually changed.
        props = extraction.extract(redact(body.text, load_case(body.session_id)))
        target_type = body.decision_type or next((p.decision_type for p in props if p.decision_type != "other"), None)
        p = next((x for x in props if x.decision_type == target_type), None)
        if p is not None:
            body.threshold_minutes = body.threshold_minutes or p.threshold_minutes
            body.escalation = body.escalation or p.escalation
            body.exception = body.exception or p.exception
        elif target_type is None:
            # Category unclear: a bare number most likely corrects the connection floor.
            n = extraction.find_threshold(body.text) or extraction._bare_number(body.text)
            esc = extraction.find_escalation(body.text)
            target_type = "authority_boundary" if esc else ("connection_risk" if n else None)
            body.threshold_minutes, body.escalation = n, esc
        body.decision_type = target_type  # type: ignore[assignment]
        body.note = body.note or body.text
    if body.rule_id:
        rule = get_rule(body.rule_id)
    else:
        rule = next((r for r in session_rules if r.decision_type == body.decision_type), None)
        if rule is None:
            raise HTTPException(404, "no rule matches this correction")
    for field, attr in (("threshold_minutes", "threshold_min"), ("escalation", "escalation"),
                        ("exception", "exception"), ("reason", "reason")):
        val = getattr(body, field)
        if val is not None:
            setattr(rule, attr, val)
    rule.corrections += 1
    rule.expert_confirmed = False
    if body.note:
        rule.notes.append(f"Correction: {redact(body.note, load_case(body.session_id))}")
    save_rule(rule)
    state = db.get_state(body.session_id)
    state["corrections"] = int(state.get("corrections", 0)) + 1
    state["teachback_confirmed"] = False
    db.set_state(body.session_id, state)
    return {"rule": rule.model_dump(), "debrief": get_debrief(body.session_id)}


# ------------------------------------------------------------------ debrief
@app.get("/api/debrief/{session_id}")
def get_debrief(session_id: str):
    return debrief_engine.status(load_case(session_id), rules_for(session_id), db.get_state(session_id))


@app.post("/api/debrief/answer")
def answer_gap(body: GapAnswerIn):
    _guard_off_record(body.session_id)
    case = load_case(body.session_id)
    state = db.get_state(body.session_id)
    gaps = {g["gap_id"]: g for g in debrief_engine.compute_gaps(case, rules_for(body.session_id), state)}
    gap = gaps.get(body.gap_id)
    if gap is None:
        raise HTTPException(404, f"gap {body.gap_id} is not open")
    answer = redact(body.answer, case)
    if gap["rule_id"]:
        rule = get_rule(gap["rule_id"])
        fields: dict[str, Any] = {}
        if gap["field"] == "threshold":
            fields["threshold_minutes"] = body.threshold_minutes
        elif gap["field"] == "escalation":
            fields["escalation"] = body.escalation
        elif gap["field"] == "exception":
            fields["exception"] = body.exception
        if not any(fields.values()):
            fields = extraction.merge_into({}, answer, gap["field"])
        if fields.get("threshold_minutes"):
            rule.threshold_min = fields["threshold_minutes"]
        if fields.get("escalation"):
            rule.escalation = fields["escalation"]
        if fields.get("exception"):
            rule.exception = fields["exception"]
        if answer:
            if rule.quote:
                rule.notes.append(f"Debrief: {answer}")
            else:
                rule.quote = answer
        rule.confidence = round(min(0.95, rule.confidence + 0.05), 2)
        save_rule(rule)
        resolved = (gap["field"] != "threshold" or rule.threshold_min) and (gap["field"] != "escalation" or rule.escalation)
    elif gap["gap_id"].startswith("missing:"):
        cat = gap["category"]
        props = [p for p in extraction.extract(answer) if p.decision_type == cat] or \
                [extraction.RuleProposal(decision_type=cat, reason=answer or "stated in debrief",
                                         threshold_minutes=body.threshold_minutes or extraction.find_threshold(answer),
                                         escalation=body.escalation or extraction.find_escalation(answer))]
        p = props[0]
        record(body.session_id, cat, p.reason, threshold=body.threshold_minutes or p.threshold_minutes,
               escalation=body.escalation or p.escalation, exception=p.exception, quote=answer,
               confidence=0.75, extracted_by="debrief")
        resolved = True
    else:  # unseen-case question: keep the note, and harvest any rule details it contains
        state.setdefault("unseen_notes", []).append({"gap_id": body.gap_id, "answer": answer})
        if "no_bag" in body.gap_id:
            r = next((x for x in rules_for(body.session_id) if x.decision_type == "connection_risk"), None)
            if r and not r.exception:
                r.exception = f"carry-on only: {answer[:160]}"
                save_rule(r)
        resolved = True
    state = db.get_state(body.session_id) if not gap["gap_id"].startswith("unseen") else state
    if resolved and body.gap_id not in state.setdefault("answered_gaps", []):
        state["answered_gaps"].append(body.gap_id)
    db.set_state(body.session_id, state)
    return {"resolved": bool(resolved), "debrief": get_debrief(body.session_id)}


@app.post("/api/debrief/confirm")
def confirm_teachback(body: ConfirmIn):
    st = get_debrief(body.session_id)
    if st["mandatory_open"]:
        raise HTTPException(409, f"{st['mandatory_open']} mandatory gap(s) still open")
    for r in rules_for(body.session_id):
        r.expert_confirmed = True
        save_rule(r)
    state = db.get_state(body.session_id)
    state["teachback_confirmed"] = True
    db.set_state(body.session_id, state)
    return get_debrief(body.session_id)


# ------------------------------------------------------------------ work map
@app.get("/api/workmap/{session_id}")
def get_workmap(session_id: str):
    return workmap.build(session_id)


@app.get("/api/workmap/{session_id}/export", response_class=PlainTextResponse)
def export_workmap(session_id: str):
    return workmap.export_markdown(session_id)


# ---------------------------------------------------------------- guardrails
@app.post("/api/guardrails/evaluate")
def evaluate_action(body: ActionIn):
    s = _session(body.session_id)
    case = load_case(body.session_id)
    source = s["expert_session_id"] if s["mode"] == "trainee" else body.session_id
    rules = rules_for(source) if source else []
    violations, warnings, facts = evaluate(case, body.option_id, rules, body.has_supervisor_approval)
    expert_name = db.get_state(body.session_id).get("expert_name", "The expert")
    blocking = body.type == "confirm" and bool(violations) and s["mode"] == "trainee"
    payload = {
        "allowed": not blocking,
        "facts": facts,
        "violations": [tutor.intervention(case, r, facts, expert_name) for r in violations],
        "warnings": [tutor.intervention(case, r, facts, expert_name) for r in warnings],
        "rules_checked": len(rules),
    }
    if s["mode"] == "trainee":
        ts = db.session_ts(body.session_id)
        if blocking:
            db.execute("INSERT INTO interventions (id, session_id, ts, json) VALUES (?,?,?,?)",
                       (db.new_id("I"), body.session_id, ts, db.dumps({"kind": "block", "option_id": body.option_id,
                                                                       "rule_ids": [r.rule_id for r in violations]})))
        elif body.type == "confirm":
            state = db.get_state(body.session_id)
            state["final"] = {"option_id": body.option_id, "clean": not violations, "ts": ts,
                              "approval": body.has_supervisor_approval}
            db.set_state(body.session_id, state)
    return payload


# ------------------------------------------------------------------- trainee
@app.post("/api/trainee/answer")
def trainee_answer(body: TraineeAnswerIn):
    s = _session(body.session_id)
    case = load_case(body.session_id)
    rules = [r for r in rules_for(s["expert_session_id"]) if r.expert_confirmed] if s["expert_session_id"] else []
    applicable = tutor.applicable_rules(case, rules)
    state = db.get_state(body.session_id)
    text = redact(body.text, case)
    if body.kind == "prediction":
        hits = tutor.match_prediction(text, case, applicable)
        state.setdefault("predictions", []).append({"text": text, "matched_rules": hits})
        db.set_state(body.session_id, state)
        return {"matched_rules": hits, "correct": bool(hits)}
    rule_id = body.rule_id
    if rule_id is None:
        blocks = db.query("SELECT json FROM interventions WHERE session_id=? ORDER BY ts DESC, rowid DESC", (body.session_id,))
        ids = list(dict.fromkeys(rid for block in blocks
                                 for rid in db.loads(block["json"]).get("rule_ids", [])))
        # An answer without an explicit target can refer to an earlier block.
        # Match only rules actually encountered, keeping the latest for feedback
        # when the explanation does not match any of them.
        rule_id = next((rid for rid in ids
                        if any(r.rule_id == rid and tutor.judge_answer(text, r) for r in rules)),
                       ids[0] if ids else None)
    rule = next((r for r in rules if r.rule_id == rule_id), None)
    correct = bool(rule and tutor.judge_answer(text, rule))
    state.setdefault("explanations", []).append({"rule_id": rule_id, "text": text, "correct": correct})
    db.set_state(body.session_id, state)
    return {"rule_id": rule_id, "correct": correct,
            "feedback": ("Exactly." if correct else f"Not quite. {rule.guardrail}") if rule else "No active intervention."}


@app.get("/api/mastery/{session_id}")
def get_mastery(session_id: str):
    s = _session(session_id)
    rules = rules_for(s["expert_session_id"]) if s["expert_session_id"] else []
    return tutor.mastery(load_case(session_id), rules, session_id)


# --------------------------------------------------------------- elevenlabs
def _agent_id(mode: str) -> Optional[str]:
    return os.environ.get(f"ELEVENLABS_AGENT_ID_{mode.upper()}") or os.environ.get("ELEVENLABS_AGENT_ID")


@app.get("/api/elevenlabs/session")
def elevenlabs_session(mode: str = "expert"):
    """Hands the browser a signed URL (private agent) or the public agent id."""
    agent_id = _agent_id(mode)
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not agent_id:
        return {"available": False, "reason": "ELEVENLABS_AGENT_ID not set: use the simulated agent"}
    if not key:
        return {"available": True, "agent_id": agent_id}
    try:
        r = httpx.get("https://api.elevenlabs.io/v1/convai/conversation/get-signed-url",
                      params={"agent_id": agent_id}, headers={"xi-api-key": key}, timeout=10)
        r.raise_for_status()
        return {"available": True, "signed_url": r.json()["signed_url"]}
    except Exception as exc:  # fall back to public agent id
        log.warning("signed url failed: %s", exc)
        return {"available": True, "agent_id": agent_id, "warning": "signed URL failed; using public agent id"}


# ----------------------------------------------------------------- external
@app.get("/api/external/flights")
def external_flights(origin: str, destination: str, date: Optional[str] = None):
    data, label = live.search_alternatives(origin, destination, date)
    return {"source": label, "itineraries": data}


@app.get("/api/external/status")
def external_status(flight: str):
    data, label = live.get_flight_status(flight)
    return {"source": label, "status": data}


@app.get("/api/external/weather")
def external_weather(iata: str):
    data, label = live.get_weather(iata.upper())
    return {"source": label, "weather": data}
