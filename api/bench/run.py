"""SkyMentor benchmark: simulated experts with hidden rules vs. the real backend.

Each session: a simulated expert with a random hidden policy works case A
(actions derived from the hidden rules), answers the apprentice's live
questions and the debrief, and corrects the teach-back. We then score what the
system learned against the hidden policy:

- field accuracy: connection floor, deadline margin, approver
- Z3 equivalence: do the learned guardrails block exactly what the hidden
  policy blocks? (a proof, or a concrete counterexample booking)
- sampled agreement on random bookings: unsafe allows and over-blocks
- effort: live questions, debrief questions, corrections, LLM calls

Usage (from api/):
  python -m bench.run --expert template --extractor heuristic --languages en --n 100
  python -m bench.run --expert template --extractor llm --languages en,fr,de,hi --n 5
"""
from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

os.environ["SKYMENTOR_OFFLINE"] = "1"
os.environ["SKYMENTOR_DATA_DIR"] = tempfile.mkdtemp(prefix="skymentor-bench-")

import logging  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.engine import extraction, verify  # noqa: E402
from app.engine.rules import evaluate, violates  # noqa: E402
from app.main import app  # noqa: E402  (loads api/.env)
from app.models import Case, LearnedRule  # noqa: E402

from .experts import HttpxShim, LLMExpert, Profile, RateLimiter, TemplateExpert  # noqa: E402

for noisy in ("skymentor", "httpx"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
RESULTS = Path(__file__).resolve().parent / "results"
c = TestClient(app)


# ------------------------------------------------------------------ session
def expert_actions(case: Case, hidden: list[LearnedRule]) -> list[tuple[str, str | None]]:
    """What an expert holding the hidden policy does on this case."""
    actions: list[tuple[str, str | None]] = [("case_opened", None)]
    allowed = []
    for alt in case.alternatives:
        blocking, _, _ = evaluate(case, alt.id, hidden)
        if not blocking:
            allowed.append(alt)
        elif all(r.decision_type == "authority_boundary" for r in blocking):
            actions.append(("escalation_requested", alt.id))
        else:
            actions.append(("alternative_rejected", alt.id))
    if allowed:
        best = min(allowed, key=lambda a: (-a.connection_min, a.price_eur))  # most reliable
        actions += [("alternative_selected", best.id), ("rebook_confirmed", best.id)]
    return actions


def screen_context(case: Case, event: str, option_id: str | None) -> str:
    if not option_id:
        return case.briefing
    a = case.option(option_id)
    verb = {"alternative_rejected": "rejected", "escalation_requested": "asked for approval on",
            "alternative_selected": "selected", "rebook_confirmed": "confirmed"}.get(event, "looked at")
    return (f"You just {verb} option {a.id} ({a.label}): {a.connection_min}-min connection, lands {a.arrival} "
            f"(passenger deadline {case.passenger.arrival_deadline}), {a.cabin}. Passenger has "
            f"{'a checked bag' if case.passenger.checked_bag else 'carry-on only'} and an {case.passenger.original_cabin} ticket.")


def agent_fields(answer: str, category: str | None, mode: str) -> dict[str, Any]:
    """Emulate the voice agent filling tool arguments from the expert's words."""
    if mode != "llm" or category not in ("connection_risk", "customer_deadline", "authority_boundary"):
        return {}
    props = extraction.llm_extract(answer) or []
    p = next((x for x in props if x.decision_type == category), None)
    if p is None:
        return {}
    return {k: v for k, v in {"threshold_minutes": p.threshold_minutes, "escalation": p.escalation,
                              "exception": p.exception}.items() if v is not None}


def run_session(profile: Profile, expert: TemplateExpert, extractor: str, limiter: RateLimiter) -> dict[str, Any]:
    t0, calls0 = time.time(), limiter.calls
    lang = profile.language
    s = c.post("/api/sessions", json={"mode": "expert", "expert_name": "Claire", "language": lang, "live": False}).json()
    sid = s["session_id"]
    case = Case.model_validate(s["case"])
    hidden = profile.hidden_rules()
    transcript: list[dict[str, str]] = []
    live_q = 0

    for event, option_id in expert_actions(case, hidden):
        resp = c.post("/api/events", json={"session_id": sid, "type": event, "option_id": option_id,
                                           "snapshot": {"selected": option_id}}).json()
        q = resp.get("question")
        if not q:
            continue
        live_q += 1
        c.post(f"/api/questions/{q['id']}/asked")
        answer = expert.answer_live(q["text"], q["category"], screen_context(case, event, option_id))
        transcript += [{"role": "agent", "text": q["text"]}, {"role": "expert", "text": answer}]
        c.post("/api/transcript", json={"session_id": sid, "role": "agent", "text": q["text"]})
        c.post("/api/transcript", json={"session_id": sid, "role": "user", "text": answer})
        c.post("/api/rules/extract", json={"session_id": sid, "text": answer})

    debrief_q, corrections, stuck, confirmed = 0, 0, False, False
    tries: dict[str, int] = {}
    for _ in range(16):
        d = c.get(f"/api/debrief/{sid}").json()
        if not d["ready_for_teachback"]:
            if not d["gaps"]:
                stuck = True
                break
            gap = d["gaps"][0]
            tries[gap["gap_id"]] = tries.get(gap["gap_id"], 0) + 1
            if tries[gap["gap_id"]] > 2:
                stuck = True
                break
            answer = expert.answer_gap(gap)
            transcript += [{"role": "agent", "text": gap["question"]}, {"role": "expert", "text": answer}]
            fields = agent_fields(answer, gap["category"], extractor)
            c.post("/api/debrief/answer", json={"session_id": sid, "gap_id": gap["gap_id"], "answer": answer, **fields})
            debrief_q += 1
            continue
        rules_now = [r for r in c.get(f"/api/rules/{sid}").json() if r["decision_type"] != "other"]
        review = expert.review_teachback(d["teachback"], rules_now)
        transcript += [{"role": "agent", "text": d["teachback"]}, {"role": "expert", "text": review.get("text", "")}]
        if review.get("confirm") or corrections >= 3:
            c.post("/api/debrief/confirm", json={"session_id": sid})
            confirmed = bool(review.get("confirm"))
            break
        corrections += 1
        dt = review.get("decision_type")
        body = {"session_id": sid, "text": review.get("text", ""), "decision_type": dt,
                **agent_fields(review.get("text", ""), dt, extractor)}
        if c.post("/api/rules/correct", json=body).status_code != 200:
            stuck = True
            break

    learned = [LearnedRule.model_validate(r) for r in c.get(f"/api/rules/{sid}").json()]
    return score(profile, hidden, learned) | {
        "session_id": sid, "live_questions": live_q, "debrief_questions": debrief_q, "corrections": corrections,
        "teachback_confirmed": confirmed, "stuck": stuck, "llm_calls": limiter.calls - calls0,
        "seconds": round(time.time() - t0, 2), "transcript": transcript,
    }


# ------------------------------------------------------------------ scoring
def score(profile: Profile, hidden: list[LearnedRule], learned: list[LearnedRule]) -> dict[str, Any]:
    confirmed = [r for r in learned if r.expert_confirmed]
    by = {r.decision_type: r for r in confirmed}
    conn, dl, auth = by.get("connection_risk"), by.get("customer_deadline"), by.get("authority_boundary")
    fields = {
        "connection_correct": bool(conn and conn.threshold_min == profile.connection_min),
        "deadline_correct": bool(dl and (dl.threshold_min or 0) == profile.deadline_margin),
        "approver_correct": bool(auth and profile.approver_matches(auth.escalation)),
    }
    same, witness = verify.equivalent(hidden, confirmed)
    rng = random.Random(profile.seed)
    unsafe = over = 0
    n = 4000
    for _ in range(n):
        has_conn = rng.random() < 0.85
        f = {"checked_bag": rng.random() < 0.6, "has_connection": has_conn,
             "connection_min": rng.randint(20, 180) if has_conn else 0, "arrival_margin_min": rng.randint(-120, 180),
             "cabin_change": rng.random() < 0.25, "has_supervisor_approval": rng.random() < 0.3}
        h = any(violates(r, f) for r in hidden)
        l = any(violates(r, f) for r in confirmed)
        unsafe += h and not l
        over += l and not h
    return {
        "profile": profile.as_dict(), **fields,
        "field_accuracy": round(sum(fields.values()) / 3, 3), "all_correct": all(fields.values()),
        "z3_equivalent": same, "counterexample": verify.describe(witness) if witness else None,
        "unsafe_allow_rate": unsafe / n, "over_block_rate": over / n,
        "learned": {r.decision_type: {"threshold": r.threshold_min, "escalation": r.escalation,
                                      "confirmed": r.expert_confirmed} for r in learned if r.decision_type != "other"},
    }


# ------------------------------------------------------------------- report
def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def mean(k):
        return round(statistics.fmean(float(r[k]) for r in rows), 3) if rows else None
    return {"n": len(rows), **{k: mean(k) for k in (
        "connection_correct", "deadline_correct", "approver_correct", "field_accuracy", "all_correct",
        "z3_equivalent", "unsafe_allow_rate", "over_block_rate", "live_questions", "debrief_questions",
        "corrections", "teachback_confirmed", "stuck", "llm_calls", "seconds")}}


def pct(x):
    return "–" if x is None else f"{100 * x:.0f}%"


def markdown(meta: dict[str, Any], groups: dict[str, dict[str, Any]], rows: list[dict[str, Any]]) -> str:
    out = [f"# SkyMentor benchmark · {meta['started']}", "",
           f"Expert: **{meta['expert']}** · extractor: **{meta['extractor']}** · {meta['n_sessions']} sessions · "
           f"seed {meta['seed']} · {meta['llm_calls']} LLM calls · {meta['minutes']} min", "",
           "| Group | n | Connection | Deadline | Approver | All 3 right | Z3-equivalent | Unsafe allows | Over-blocks "
           "| Live Qs | Debrief Qs | Corrections | Confirmed | LLM calls |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, g in groups.items():
        out.append(f"| {name} | {g['n']} | {pct(g['connection_correct'])} | {pct(g['deadline_correct'])} | "
                   f"{pct(g['approver_correct'])} | {pct(g['all_correct'])} | {pct(g['z3_equivalent'])} | "
                   f"{100 * g['unsafe_allow_rate']:.1f}% | {100 * g['over_block_rate']:.1f}% | {g['live_questions']:.1f} | "
                   f"{g['debrief_questions']:.1f} | {g['corrections']:.1f} | {pct(g['teachback_confirmed'])} | {g['llm_calls']:.1f} |")
    fails = [r for r in rows if not r["z3_equivalent"]][:8]
    if fails:
        out += ["", "## Counterexamples (Z3)", "",
                "Bookings where the learned guardrails and the expert's hidden policy disagree:", ""]
        for r in fails:
            p = r["profile"]
            out.append(f"- `{r['session_id']}` ({p['language']}, floor {p['connection_min']}, margin {p['deadline_margin']}, "
                       f"{p['approver']}): learned {json.dumps(r['learned'], ensure_ascii=False)} → {r['counterexample']}")
    out += ["", "Unsafe allow = the hidden policy blocks a random booking but the learned rules allow it. "
            "Z3-equivalent = proven to block exactly the same bookings as the hidden policy."]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=10, help="sessions per language")
    ap.add_argument("--languages", default="en")
    ap.add_argument("--expert", choices=["template", "llm"], default="template")
    ap.add_argument("--extractor", choices=["llm", "heuristic"], default="heuristic")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--rpm", type=float, default=float(os.environ.get("BENCH_RPM", 4.5)),
                    help="Cerebras requests per minute (free tier: 5)")
    ap.add_argument("--name", default=None, help="results file name (default: timestamp)")
    ap.add_argument("--seeds", default=None, help="replay exact profiles, e.g. 100003:hi,100010:en (overrides --n)")
    args = ap.parse_args(argv)

    needs_llm = args.expert == "llm" or args.extractor == "llm"
    if needs_llm and not os.environ.get("CEREBRAS_API_KEY"):
        sys.exit("CEREBRAS_API_KEY is not set (put it in api/.env)")
    limiter = RateLimiter(args.rpm)
    if args.extractor == "llm":
        extraction.httpx = HttpxShim(limiter)  # backend extraction shares the benchmark's quota
    else:
        extraction.llm_extract = lambda *a, **k: None  # deterministic heuristic extractor only

    RESULTS.mkdir(exist_ok=True)
    name = args.name or time.strftime("%Y%m%d-%H%M%S")
    jsonl = RESULTS / f"{name}.jsonl"
    started, rows = time.strftime("%Y-%m-%d %H:%M"), []
    langs = [x.strip() for x in args.languages.split(",") if x.strip()]
    if args.seeds:
        plan = [(int(x.split(":")[0]), x.split(":")[1]) for x in args.seeds.split(",")]
    else:
        plan = [(args.seed * 100_000 + i * 10 + langs.index(lang), lang) for i in range(args.n) for lang in langs]
    langs = list(dict.fromkeys(lang for _, lang in plan))
    total = len(plan)
    t0 = time.time()
    with jsonl.open("w") as fh:
        for seed, lang in plan:
            profile = Profile.random(seed, lang)
            expert = LLMExpert(profile, limiter) if args.expert == "llm" else TemplateExpert(profile)
            try:
                row = run_session(profile, expert, args.extractor, limiter)
            except Exception as exc:  # keep going; a crashed session counts as a failure
                row = score(profile, profile.hidden_rules(), []) | {
                    "session_id": "error", "error": repr(exc), "live_questions": 0, "debrief_questions": 0,
                    "corrections": 0, "teachback_confirmed": False, "stuck": True, "llm_calls": 0, "seconds": 0}
            row["group"] = f"{args.expert}/{args.extractor}/{lang}"
            rows.append(row)
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            print(f"[{len(rows)}/{total}] {row['group']} floor={profile.connection_min} margin={profile.deadline_margin} "
                  f"approver={profile.approver}: fields={row['field_accuracy']:.2f} z3={'✓' if row['z3_equivalent'] else '✗'} "
                  f"q={row['live_questions']}+{row['debrief_questions']} corr={row['corrections']} "
                  f"calls={row['llm_calls']} {row['seconds']}s", flush=True)

    groups = {g: summarize([r for r in rows if r["group"] == g]) for g in dict.fromkeys(r["group"] for r in rows)}
    if len(groups) > 1:
        groups["all"] = summarize(rows)
    meta = {"started": started, "expert": args.expert, "extractor": args.extractor, "seed": args.seed,
            "languages": langs, "n_sessions": len(rows), "llm_calls": limiter.calls, "rate_limit_retries": limiter.retries,
            "minutes": round((time.time() - t0) / 60, 1)}
    (RESULTS / f"{name}.json").write_text(json.dumps({"meta": meta, "groups": groups}, indent=2, ensure_ascii=False))
    md = markdown(meta, groups, rows)
    (RESULTS / f"{name}.md").write_text(md)
    print("\n" + md)


if __name__ == "__main__":
    main()
