"""PII redaction applied before any transcript or event text is stored.

Lightweight regex + case-aware redaction. Swap in Microsoft Presidio
(`presidio-analyzer`) if you need broader entity coverage.
"""
from __future__ import annotations

import re
from typing import Optional

from ..models import Case

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
PASSPORT = re.compile(r"\b[A-Z]{2}\d{7}\b")
CARD = re.compile(r"\b(?:\d[ -]?){13,16}\b")


def redact(text: str, case: Optional[Case] = None) -> str:
    out = EMAIL.sub("[EMAIL]", text)
    out = CARD.sub("[CARD]", out)
    out = PHONE.sub("[PHONE]", out)
    out = PASSPORT.sub("[PASSPORT]", out)
    if case is not None:
        p = case.passenger
        out = re.sub(re.escape(p.pnr), "[PNR]", out, flags=re.IGNORECASE)
        names = [p.name] + p.name.split()
        for name in sorted(names, key=len, reverse=True):
            if len(name) >= 3:
                out = re.sub(rf"\b{re.escape(name)}\b", "[PASSENGER]", out, flags=re.IGNORECASE)
        out = re.sub(r"\[PASSENGER\](\s+\[PASSENGER\])+", "[PASSENGER]", out)
    return out
