# SkyMentor benchmark · 2026-10-04 09:43

Expert: **template** · extractor: **llm** · 16 sessions · seed 1 · 72 LLM calls · 15.8 min

| Group | n | Connection | Deadline | Approver | All 3 right | Z3-equivalent | Unsafe allows | Over-blocks | Live Qs | Debrief Qs | Corrections | Confirmed | LLM calls |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| template/llm/en | 4 | 100% | 100% | 100% | 100% | 100% | 0.0% | 0.0% | 3.0 | 3.0 | 0.2 | 100% | 4.2 |
| template/llm/fr | 4 | 100% | 100% | 100% | 100% | 100% | 0.0% | 0.0% | 3.0 | 3.0 | 0.8 | 100% | 4.5 |
| template/llm/de | 4 | 100% | 100% | 100% | 100% | 100% | 0.0% | 0.0% | 3.0 | 3.0 | 0.0 | 100% | 3.8 |
| template/llm/hi | 4 | 100% | 100% | 100% | 100% | 100% | 0.0% | 0.0% | 3.0 | 3.0 | 0.8 | 100% | 5.5 |
| all | 16 | 100% | 100% | 100% | 100% | 100% | 0.0% | 0.0% | 3.0 | 3.0 | 0.4 | 100% | 4.5 |

Unsafe allow = the hidden policy blocks a random booking but the learned rules allow it. Z3-equivalent = proven to block exactly the same bookings as the hidden policy.
