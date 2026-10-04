# SkyMentor benchmark · 2026-10-04 09:59

Expert: **llm** · extractor: **llm** · 8 sessions · seed 1 · 99 LLM calls · 21.8 min

| Group | n | Connection | Deadline | Approver | All 3 right | Z3-equivalent | Unsafe allows | Over-blocks | Live Qs | Debrief Qs | Corrections | Confirmed | LLM calls |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| llm/llm/en | 2 | 100% | 100% | 100% | 100% | 100% | 0.0% | 0.0% | 2.5 | 3.0 | 1.5 | 50% | 13.5 |
| llm/llm/fr | 2 | 100% | 100% | 100% | 100% | 100% | 0.0% | 0.0% | 2.5 | 3.0 | 1.0 | 100% | 12.0 |
| llm/llm/de | 2 | 100% | 100% | 100% | 100% | 100% | 0.0% | 0.0% | 3.0 | 3.0 | 0.0 | 100% | 10.5 |
| llm/llm/hi | 2 | 100% | 100% | 100% | 100% | 100% | 0.0% | 0.0% | 2.5 | 3.0 | 1.5 | 50% | 13.5 |
| all | 8 | 100% | 100% | 100% | 100% | 100% | 0.0% | 0.0% | 2.6 | 3.0 | 1.0 | 75% | 12.4 |

Unsafe allow = the hidden policy blocks a random booking but the learned rules allow it. Z3-equivalent = proven to block exactly the same bookings as the hidden policy.
