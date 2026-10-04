"""Offline benchmark smoke test: template experts (English, heuristic extractor)
must be learned exactly. Guards the zero-margin and "station supervisor" fixes."""
import os

os.environ.setdefault("CEREBRAS_API_KEY", "")  # stay offline even if api/.env has a key

from bench.experts import Profile, RateLimiter, TemplateExpert  # noqa: E402
from bench.run import run_session  # noqa: E402


def test_template_experts_are_learned_exactly():
    for seed in range(6):
        p = Profile.random(seed, "en")
        p.deadline_margin = 0 if seed % 2 else 30
        p.approver = "station supervisor" if seed % 3 == 0 else p.approver
        row = run_session(p, TemplateExpert(p), "heuristic", RateLimiter(10_000))
        assert row["teachback_confirmed"] and not row["stuck"], row["transcript"][-4:]
        assert row["all_correct"] and row["z3_equivalent"], row["learned"]
