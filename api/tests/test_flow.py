"""End-to-end Capture -> Map -> Teach loop against the API, fully offline."""
import os
import tempfile

os.environ["SKYMENTOR_OFFLINE"] = "1"
os.environ["SKYMENTOR_DATA_DIR"] = tempfile.mkdtemp()
os.environ.pop("CEREBRAS_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

c = TestClient(app)


def ask_and_answer(sid, ev_resp, answer):
    q = ev_resp["question"]
    assert q, ev_resp["score"]
    c.post(f"/api/questions/{q['id']}/asked")
    c.post("/api/transcript", json={"session_id": sid, "role": "agent", "text": q["text"]})
    c.post("/api/transcript", json={"session_id": sid, "role": "user", "text": answer})
    r = c.post("/api/rules/extract", json={"session_id": sid, "text": answer})
    assert r.status_code == 200, r.text
    return q, r.json()


def test_full_loop():
    c.post("/api/reset")
    s = c.post("/api/sessions", json={"mode": "expert", "expert_name": "Claire"}).json()
    sid = s["session_id"]
    assert s["case"]["case_id"] == "case_A"
    c.post("/api/events", json={"session_id": sid, "type": "case_opened"})

    # --- Capture: three live questions, guardrails among them
    ev = c.post("/api/events", json={"session_id": sid, "type": "alternative_rejected", "option_id": "A",
                                     "snapshot": {"selected": None}}).json()
    q1, r1 = ask_and_answer(sid, ev, "55 minutes with a checked bag in Doha is too tight, Maria Chen's bag won't make it. I never go below 75 minutes with a bag.")
    assert q1["is_guardrail"] and r1["rules"][0]["threshold_min"] == 75
    assert "[PASSENGER]" in r1["rules"][0]["quote"]  # PII redacted

    ev = c.post("/api/events", json={"session_id": sid, "type": "alternative_rejected", "option_id": "C"}).json()
    q2, r2 = ask_and_answer(sid, ev, "Helsinki lands at 10:25, after her deadline, she would miss the signing.")
    assert r2["rules"][0]["decision_type"] == "customer_deadline"

    ev = c.post("/api/events", json={"session_id": sid, "type": "escalation_requested", "option_id": "D"}).json()
    q3, r3 = ask_and_answer(sid, ev, "That's an upgrade to business. I can't approve that myself, it needs sign-off.")
    assert q3["is_guardrail"]

    # Selecting London after everything is explained: ask less
    ev = c.post("/api/events", json={"session_id": sid, "type": "alternative_selected", "option_id": "B"}).json()
    assert ev["question"] is None

    # Off the record: no question, nothing stored
    c.post(f"/api/sessions/{sid}/off_record", json={"on": True})
    ev = c.post("/api/events", json={"session_id": sid, "type": "alternative_inspected", "option_id": "A"}).json()
    assert ev["off_record"] and ev["question"] is None
    assert c.post("/api/rules/extract", json={"session_id": sid, "text": "between us, the bag rule is 60"}).status_code == 409
    c.post(f"/api/sessions/{sid}/off_record", json={"on": False})
    c.post("/api/events", json={"session_id": sid, "type": "rebook_confirmed", "option_id": "B"})

    # --- Map: debrief closes gaps (>=3 answered), teach-back, correction, confirm
    d = c.get(f"/api/debrief/{sid}").json()
    assert d["mandatory_open"] >= 2 and not d["ready_for_teachback"]
    answers = {"threshold": "At least 30 minutes of margin before the deadline.",
               "escalation": "The duty manager on shift has to approve it.",
               "exception": "No exceptions, never."}
    n = 0
    while not d["ready_for_teachback"]:
        gap = d["gaps"][0]
        ans = answers.get(gap["field"], "With carry-on only I'd accept 60 minutes.")
        c.post("/api/questions", json={"session_id": sid, "text": gap["question"]})
        d = c.post("/api/debrief/answer", json={"session_id": sid, "gap_id": gap["gap_id"], "answer": ans}).json()["debrief"]
        n += 1
        assert n < 10
    assert d["answered"] >= 3 and "75 minutes" in d["teachback"]
    conn_rule = next(r for r in c.get(f"/api/rules/{sid}").json() if r["decision_type"] == "connection_risk")
    d = c.post("/api/rules/correct", json={"session_id": sid, "rule_id": conn_rule["rule_id"], "threshold_minutes": 80,
                                           "note": "Actually make it 80"}).json()["debrief"]
    assert d["corrections"] == 1 and "80 minutes" in d["teachback"]
    # free-text correction, as the simulated agent / correct_rule tool sends it
    d = c.post("/api/rules/correct", json={"session_id": sid, "text": "No, upgrades go to the duty supervisor, not the manager."}).json()["debrief"]
    assert d["corrections"] == 2 and "duty supervisor" in d["teachback"], d["teachback"]
    conn_rule = next(r for r in c.get(f"/api/rules/{sid}").json() if r["decision_type"] == "connection_risk")
    assert "[PASSENGER]" in conn_rule["quote"] and "80" not in conn_rule["quote"] and conn_rule["notes"]
    d = c.post("/api/debrief/confirm", json={"session_id": sid}).json()
    assert d["complete"]

    wm = c.get(f"/api/workmap/{sid}").json()
    assert wm["stats"]["live_questions"] == 3 and wm["stats"]["guardrails"] == 3
    assert all(s["ts_label"] for s in wm["steps"]) and any(s["guardrails"] for s in wm["steps"])
    assert "80 min" in c.get(f"/api/workmap/{sid}/export").text

    # --- Teach: unseen case, wrong decision caught before save
    t = c.post("/api/sessions", json={"mode": "trainee"}).json()
    tid = t["session_id"]
    assert t["expert_session_id"] == sid and t["case"]["case_id"] == "case_B"
    p = c.post("/api/trainee/answer", json={"session_id": tid, "kind": "prediction", "text": "Reykjavik looks risky"}).json()
    assert p["correct"]
    r = c.post("/api/guardrails/evaluate", json={"session_id": tid, "option_id": "A"}).json()
    assert not r["allowed"] and r["violations"][0]["decision_type"] == "connection_risk"
    assert r["violations"][0]["screen_moment"]["option_id"] == "A"
    assert c.post("/api/guardrails/evaluate", json={"session_id": tid, "option_id": "C"}).json()["allowed"] is False
    assert c.post("/api/guardrails/evaluate", json={"session_id": tid, "option_id": "D"}).json()["allowed"] is False
    assert c.post("/api/guardrails/evaluate", json={"session_id": tid, "option_id": "D", "has_supervisor_approval": True}).json()["allowed"]
    e = c.post("/api/trainee/answer", json={"session_id": tid, "kind": "explanation",
                                           "text": "The connection is too short for the checked bag"}).json()
    assert e["correct"]
    assert c.post("/api/guardrails/evaluate", json={"session_id": tid, "option_id": "B"}).json()["allowed"]
    m = c.get(f"/api/mastery/{tid}").json()
    assert m["finished"] and len(m["items"]) == 3
    print(m["summary"])
