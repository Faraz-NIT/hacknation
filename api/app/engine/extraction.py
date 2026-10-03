"""Natural-language expert answer -> typed rule proposals.

Primary path in voice mode: the ElevenLabs agent itself fills the
`record_expert_rule` client-tool schema (the agent's LLM does the extraction).
This module is the backend path used by the simulated agent, by
POST /rules/extract and as a backfill. It uses a Cerebras-hosted LLM when CEREBRAS_API_KEY is
set and a deterministic heuristic otherwise; every output is Pydantic-validated.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

import httpx
from pydantic import BaseModel, ValidationError

WORD_NUM = {
    "thirty": 30, "forty": 40, "forty-five": 45, "forty five": 45, "fifty": 50, "sixty": 60,
    "seventy": 70, "seventy-five": 75, "seventy five": 75, "eighty": 80, "ninety": 90,
    "half an hour": 30, "an hour": 60, "one hour": 60, "two hours": 120,
}

DUR = (
    r"(\d{2,3}\s*(?:min(?:ute)?s?|m\b)?"
    r"|half an hour"
    r"|(?:an|one|two)\s+hours?(?:\s+and\s+(?:a\s+half|a\s+quarter|fifteen|\d{1,2}(?:\s*min(?:ute)?s?)?))?"
    r"|seventy[- ]five|forty[- ]five|ninety|sixty|seventy|eighty|fifty|forty|thirty)"
)
QUALIFIER = (
    r"(?:at least|minimum(?: of| is)?|min(?:imum)? connection (?:of|is)|no less than|"
    r"never (?:go |book |accept )?(?:anything )?(?:below|under|less than|shorter than)|"
    r"nothing (?:under|below|shorter than|less than)|not (?:under|below|less than)|"
    r"under|below|less than|shorter than|fewer than|floor (?:of|is)|buffer (?:of|is)?|margin (?:of|is)?|"
    r"cushion (?:of|is)?)"
)
QUALIFIED = re.compile(rf"{QUALIFIER}\s+(?:about |around |roughly |maybe )?{DUR}", re.IGNORECASE)
POSTFIX = re.compile(rf"{DUR}\s+(?:is|as)\s+(?:my|the|our)\s+(?:absolute\s+)?(?:minimum|floor|limit|buffer|margin)", re.IGNORECASE)
BUFFER = re.compile(rf"{DUR}\s+(?:of\s+)?(?:buffer|margin|cushion|spare|before (?:the|her|his|their) deadline)", re.IGNORECASE)

ESCALATION = re.compile(
    r"\b(duty (?:manager|supervisor|officer)|shift (?:lead|supervisor|manager)|ops control|operations control|"
    r"station manager|team lead|revenue desk|supervisor|my manager|the manager)\b",
    re.IGNORECASE,
)
EXCEPTION = re.compile(r"\b(?:unless|except(?: when| if| for)?|only if|the (?:only )?exception (?:is|would be))\s+([^.;!?]+)", re.IGNORECASE)
NO_EXCEPTION = re.compile(r"\b(no exceptions?|never,? ever|always,? no matter|not even)\b", re.IGNORECASE)

KEYWORDS = {
    "connection_risk": ["connection", "connect", "transfer", "layover", "bag", "luggage", "baggage", "tight",
                        "misconnect", "mct", "short", "terminal", "make it"],
    "customer_deadline": ["deadline", "meeting", "signing", "appointment", "too late", "after ten", "arrive by",
                          "land by", "on time", "in time", "before ten", "well before", "miss", "commitment", "lands after", "gets in after", "late", "margin", "buffer"],
    "authority_boundary": ["upgrade", "business", "premium", "cabin", "supervisor", "approval", "approve",
                           "sign off", "sign-off", "waiver", "authoris", "authoriz", "manager", "escalat", "allowed to"],
}


def parse_duration(s: str) -> Optional[int]:
    s = s.lower().strip()
    m = re.match(r"(\d{2,3})", s)
    if m:
        return int(m.group(1))
    base = 0
    if "two hour" in s:
        base = 120
    elif "hour" in s and "half an hour" not in s:
        base = 60
    if base:
        if "half" in s:
            return base + 30
        if "quarter" in s or "fifteen" in s:
            return base + 15
        extra = re.search(r"and\s+(\d{1,2})", s)
        return base + (int(extra.group(1)) if extra else 0)
    for word, val in sorted(WORD_NUM.items(), key=lambda kv: -len(kv[0])):
        if word in s:
            return val
    return None


def find_threshold(text: str, kind: str = "any") -> Optional[int]:
    patterns = [QUALIFIED, POSTFIX] + ([BUFFER] if kind in ("deadline", "any") else [])
    for pat in patterns:
        for m in pat.finditer(text):
            val = parse_duration(m.group(1))
            if val and 10 <= val <= 300:
                return val
    return None


def find_escalation(text: str) -> Optional[str]:
    m = ESCALATION.search(text)
    if not m:
        return None
    who = m.group(1).lower().replace("my ", "").replace("the ", "")
    return who if who != "manager" else "the manager"


def find_exception(text: str) -> Optional[str]:
    m = EXCEPTION.search(text)
    if m:
        return m.group(1).strip()[:180]
    if NO_EXCEPTION.search(text):
        return "none - expert says no exceptions"
    return None


def _clauses(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?;])\s+|\s+(?:and also|but|whereas|also)\s+|,\s+(?:and|but)\s+", text)
    return [p.strip() for p in parts if p and p.strip()]


def classify(text: str) -> dict[str, int]:
    low = text.lower()
    return {cat: sum(1 for kw in kws if kw in low) for cat, kws in KEYWORDS.items()}


class RuleProposal(BaseModel):
    decision_type: str
    reason: str
    threshold_minutes: Optional[int] = None
    escalation: Optional[str] = None
    exception: Optional[str] = None
    confidence: float = 0.6
    extracted_by: str = "heuristic"


def heuristic_extract(text: str) -> list[RuleProposal]:
    grouped: dict[str, list[str]] = {}
    for clause in _clauses(text):
        scores = classify(clause)
        best = max(scores.values())
        if best == 0:
            continue
        for cat, sc in scores.items():
            if sc == best or sc >= 2:
                grouped.setdefault(cat, []).append(clause)
    proposals = []
    for cat, clauses in grouped.items():
        joined = " ".join(dict.fromkeys(clauses))
        threshold = None
        if cat == "connection_risk":
            threshold = find_threshold(joined, "connection")
        elif cat == "customer_deadline":
            threshold = find_threshold(joined, "deadline")
        proposals.append(RuleProposal(
            decision_type=cat,
            reason=joined[:240],
            threshold_minutes=threshold,
            escalation=find_escalation(joined) if cat == "authority_boundary" else None,
            exception=find_exception(joined),
            confidence=round(min(0.9, 0.55 + 0.1 * len(clauses) + (0.1 if threshold else 0)), 2),
        ))
    return proposals


LLM_SYSTEM = """You turn an airline disruption expert's spoken explanation into rule objects.
Return ONLY JSON: {"rules": [{"decision_type": "connection_risk|customer_deadline|authority_boundary|other",
"reason": "<the expert's reason, close to their words>", "threshold_minutes": int|null,
"escalation": "<who must approve>"|null, "exception": "<stated exception>"|null, "confidence": 0-1}]}
connection_risk = minimum connection time when a bag is checked (threshold = that minimum).
customer_deadline = landing too late for the passenger's commitment (threshold = required margin before deadline, null if none stated).
authority_boundary = upgrades / waivers / cabin changes needing someone's approval (escalation = who).
Never invent thresholds, people or exceptions that were not said."""


def llm_extract(text: str, context: str = "") -> Optional[list[RuleProposal]]:
    key = os.environ.get("CEREBRAS_API_KEY")
    if not key:
        return None
    try:
        r = httpx.post(
            "https://api.cerebras.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "content-type": "application/json"},
            json={
                "model": os.environ.get("CEREBRAS_MODEL", "gpt-oss-120b"),
                "max_tokens": 2000,
                "messages": [
                    {"role": "system", "content": LLM_SYSTEM},
                    {"role": "user", "content": f"Context: {context}\n\nExpert said: {text}"},
                ],
            },
            timeout=12,
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"].get("content") or ""
        payload = json.loads(content[content.find("{"): content.rfind("}") + 1])
        out = []
        for raw in payload.get("rules", []):
            try:
                out.append(RuleProposal(**raw, extracted_by="llm"))
            except ValidationError:
                continue
        return out
    except Exception:
        return None


def extract(text: str, context: str = "") -> list[RuleProposal]:
    proposals = llm_extract(text, context)
    if proposals is None:  # no key or failure -> deterministic fallback
        proposals = heuristic_extract(text)
    return proposals


def merge_into(existing: dict[str, Any], text: str, field: str) -> dict[str, Any]:
    """Debrief answers: pull one specific field out of a free-text answer."""
    if field == "threshold":
        existing["threshold_minutes"] = find_threshold(text) or _bare_number(text)
    elif field == "escalation":
        existing["escalation"] = find_escalation(text)
    elif field == "exception":
        existing["exception"] = find_exception(text) or ("none - expert says no exceptions"
                                                         if re.search(r"\bno\b|\bnever\b|\bnone\b", text, re.I) else text[:180])
    return existing


def _bare_number(text: str) -> Optional[int]:
    m = re.search(DUR, text, re.IGNORECASE)
    if m:
        val = parse_duration(m.group(1))
        if val and 10 <= val <= 300:
            return val
    return None
