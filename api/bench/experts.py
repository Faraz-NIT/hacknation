"""Simulated experts with hidden rules, plus a rate-limited Cerebras client.

Two expert backends:
- TemplateExpert: fast, free, deterministic per seed. Picks the topic from the
  question's category / gap id and answers from phrases.py, sometimes vaguely.
- LLMExpert: a Cerebras persona that only sees the raw question text, so it
  also tests whether the questions themselves are understandable.
"""
from __future__ import annotations

import json
import os
import random
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Optional

import httpx

from app.engine.rules import refresh
from app.models import LearnedRule

from .phrases import APPROVERS, say

CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions"
NO = {"en": "No. ", "fr": "Non. ", "de": "Nein. ", "hi": "नहीं। "}
LANG_NAME = {"en": "English", "fr": "French", "de": "German", "hi": "Hindi"}


# ---------------------------------------------------------------- rate limit
class RateLimiter:
    """Shared by the expert and the backend's extractor: one Cerebras quota."""

    def __init__(self, rpm: float):
        self.interval = 60.0 / rpm
        self.lock = threading.Lock()
        self.next_at = 0.0
        self.calls = 0
        self.retries = 0

    def post(self, url: str, **kw) -> httpx.Response:
        for attempt in range(8):
            with self.lock:
                wait = self.next_at - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                self.next_at = time.monotonic() + self.interval
                self.calls += 1
            r = httpx.post(url, **kw)
            if r.status_code != 429 and r.status_code < 500:
                return r
            self.retries += 1
            delay = float(r.headers.get("retry-after") or 0) or min(120, 10 * 2 ** attempt)
            print(f"    [rate limit] HTTP {r.status_code}, waiting {delay:.0f}s", flush=True)
            time.sleep(delay)
        return r


class HttpxShim:
    """Stands in for the `httpx` module inside app.engine.extraction."""

    def __init__(self, limiter: RateLimiter):
        self.limiter = limiter

    def post(self, url: str, **kw):
        return self.limiter.post(url, **kw)


def chat(limiter: RateLimiter, system: str, user: str, temperature: float = 0.7, max_tokens: int = 1500) -> str:
    r = limiter.post(
        CEREBRAS_URL,
        headers={"Authorization": f"Bearer {os.environ['CEREBRAS_API_KEY']}", "content-type": "application/json"},
        json={"model": os.environ.get("CEREBRAS_MODEL", "gpt-oss-120b"), "max_tokens": max_tokens,
              "temperature": temperature,
              "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
        timeout=60,
    )
    r.raise_for_status()
    return (r.json()["choices"][0]["message"].get("content") or "").strip()


# ------------------------------------------------------------------- profile
@dataclass
class Profile:
    """The hidden policy a simulated expert holds."""

    seed: int
    language: str
    connection_min: int  # never book a connection shorter than this with a checked bag
    deadline_margin: int  # minutes of margin before the deadline (0 = just land before it)
    approver: str  # canonical key in APPROVERS
    vagueness: float  # chance a live answer leaves the number / approver out

    @staticmethod
    def random(seed: int, language: str) -> "Profile":
        rng = random.Random(seed)
        return Profile(seed=seed, language=language,
                       connection_min=rng.choice(range(60, 106, 5)),
                       deadline_margin=rng.choice([0, 15, 30, 45]),
                       approver=rng.choice(sorted(APPROVERS)),
                       vagueness=rng.choice([0.0, 0.3, 0.6]))

    def hidden_rules(self) -> list[LearnedRule]:
        def mk(rid, kind, threshold=None, escalation=None):
            return refresh(LearnedRule(rule_id=rid, session_id="hidden", decision_type=kind, title="", condition={},
                                       action="note", reason="hidden", threshold_min=threshold,
                                       escalation=escalation, expert_confirmed=True))
        return [mk("H1", "connection_risk", self.connection_min),
                mk("H2", "customer_deadline", self.deadline_margin or None),
                mk("H3", "authority_boundary", escalation=self.approver)]

    def approver_matches(self, captured: Optional[str]) -> bool:
        return bool(captured) and any(k in captured.lower() for k in APPROVERS[self.approver]["keywords"])

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# ------------------------------------------------------------------- experts
class TemplateExpert:
    kind = "template"

    def __init__(self, profile: Profile):
        self.p = profile
        self.rng = random.Random(profile.seed * 7919)

    def _kw(self):
        return {"T": self.p.connection_min, "M": self.p.deadline_margin,
                "A": APPROVERS[self.p.approver][self.p.language]}

    def answer_live(self, question: str, category: str, context: str) -> str:
        vague = self.rng.random() < self.p.vagueness
        lang, kw = self.p.language, self._kw()
        if category == "connection_risk":
            return say("connection_vague" if vague else "connection_direct", lang, **kw)
        if category == "customer_deadline":
            vague = vague or self.p.deadline_margin == 0
            return say("deadline_vague" if vague else "deadline_direct", lang, **kw)
        if category == "authority_boundary":
            return say("authority_vague" if vague else "authority_direct", lang, **kw)
        return say("generic", lang, **kw)

    def answer_gap(self, gap: dict[str, Any]) -> str:
        lang, kw = self.p.language, self._kw()
        cat, field, gid = gap.get("category"), gap.get("field"), gap["gap_id"]
        if gid == "unseen:no_bag":
            return say("no_bag", lang, **kw)
        if gid == "unseen:weather":
            return say("weather", lang, **kw)
        if field == "exception":
            return say("no_exception", lang, **kw)
        if cat == "connection_risk":
            return say("connection_number", lang, **kw) if field == "threshold" else say("connection_direct", lang, **kw)
        if cat == "customer_deadline":
            return say("deadline_margin" if self.p.deadline_margin else "deadline_no_margin", lang, **kw)
        if cat == "authority_boundary":
            return say("authority_who", lang, **kw) if field == "escalation" else say("authority_direct", lang, **kw)
        return say("generic", lang, **kw)

    def review_teachback(self, teachback: str, captured: list[dict[str, Any]]) -> dict[str, Any]:
        """Compare what the apprentice learned with the hidden policy; correct the first mismatch."""
        lang, kw = self.p.language, self._kw()
        by = {r["decision_type"]: r for r in captured}
        conn, dl, auth = by.get("connection_risk"), by.get("customer_deadline"), by.get("authority_boundary")
        if not conn or conn.get("threshold_min") != self.p.connection_min:
            return {"confirm": False, "decision_type": "connection_risk", "text": say("correct_connection", lang, **kw)}
        if not dl or (dl.get("threshold_min") or 0) != self.p.deadline_margin:
            key = "deadline_margin" if self.p.deadline_margin else "deadline_no_margin"
            return {"confirm": False, "decision_type": "customer_deadline", "text": NO[lang] + say(key, lang, **kw)}
        if not auth or not self.p.approver_matches(auth.get("escalation")):
            return {"confirm": False, "decision_type": "authority_boundary", "text": say("correct_authority", lang, **kw)}
        return {"confirm": True, "text": say("confirm", lang, **kw)}


class LLMExpert(TemplateExpert):
    kind = "llm"

    def __init__(self, profile: Profile, limiter: RateLimiter):
        super().__init__(profile)
        self.limiter = limiter

    def _persona(self) -> str:
        p, lang = self.p, LANG_NAME[self.p.language]
        margin = (f"keep at least {p.deadline_margin} minutes of margin before the passenger's deadline"
                  if p.deadline_margin else "never let the passenger land after their deadline (no extra margin needed)")
        return f"""You are Claire, a senior airline disruption agent, talking to an AI apprentice that watches you rebook a passenger.
Your private policy (state it only when it is relevant to the question):
- With a checked bag, never book a connection shorter than {p.connection_min} minutes.
- {margin[0].upper() + margin[1:]}.
- You may not approve cabin upgrades yourself; {p.approver} must approve them.
- No other exceptions.
Rules for answering:
- Speak only {lang}, as on a phone call: 1 to 3 short sentences, no lists, no markdown.
- Answer only what is asked. {"Often you leave out exact numbers or names unless asked for them directly." if p.vagueness >= 0.3 else "Be precise."}"""

    def answer_live(self, question: str, category: str, context: str) -> str:
        return chat(self.limiter, self._persona(), f"On screen: {context}\nApprentice asks: {question}")

    def answer_gap(self, gap: dict[str, Any]) -> str:
        return chat(self.limiter, self._persona(), f"Debrief after the task. Apprentice asks: {gap['question']}")

    def review_teachback(self, teachback: str, captured: list[dict[str, Any]]) -> dict[str, Any]:
        out = chat(self.limiter, self._persona() + """
Now judge the apprentice's summary against your private policy. Reply with JSON only:
{"confirm": true} if every number and approver is right, otherwise
{"confirm": false, "decision_type": "connection_risk|customer_deadline|authority_boundary",
 "text": "<one spoken sentence in your language correcting the first thing that is wrong>"}""",
                   f"Apprentice's summary: {teachback}", temperature=0.2)
        try:
            return json.loads(out[out.find("{"): out.rfind("}") + 1])
        except ValueError:
            return {"confirm": True, "text": out}
