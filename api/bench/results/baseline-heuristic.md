# SkyMentor benchmark · 2026-10-04 09:36

Expert: **template** · extractor: **heuristic** · 100 sessions · seed 1 · 0 LLM calls · 0.1 min

| Group | n | Connection | Deadline | Approver | All 3 right | Z3-equivalent | Unsafe allows | Over-blocks | Live Qs | Debrief Qs | Corrections | Confirmed | LLM calls |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| template/heuristic/en | 25 | 100% | 100% | 100% | 100% | 100% | 0.0% | 0.0% | 3.0 | 3.0 | 0.0 | 100% | 0.0 |
| template/heuristic/fr | 25 | 0% | 0% | 0% | 0% | 0% | 65.0% | 0.0% | 5.0 | 4.0 | 0.0 | 0% | 0.0 |
| template/heuristic/de | 25 | 44% | 44% | 44% | 44% | 44% | 36.0% | 0.0% | 5.0 | 3.0 | 0.0 | 44% | 0.0 |
| template/heuristic/hi | 25 | 0% | 0% | 0% | 0% | 0% | 64.3% | 0.0% | 5.0 | 3.0 | 0.0 | 0% | 0.0 |
| all | 100 | 36% | 36% | 36% | 36% | 36% | 41.3% | 0.0% | 4.5 | 3.2 | 0.0 | 36% | 0.0 |

## Counterexamples (Z3)

Bookings where the learned guardrails and the expert's hidden policy disagree:

- `S_87572337` (fr, floor 80, margin 15, shift lead): learned {"connection_risk": {"threshold": 80, "escalation": null, "confirmed": false}, "authority_boundary": {"threshold": null, "escalation": null, "confirmed": false}} → checked bag, 1-min connection, lands 0 min before the deadline, cabin upgrade with approval
- `S_63746289` (hi, floor 85, margin 15, duty manager): learned {"authority_boundary": {"threshold": null, "escalation": null, "confirmed": false}} → checked bag, 1-min connection, lands 0 min before the deadline, cabin upgrade with approval
- `S_2fe27edb` (fr, floor 80, margin 0, station supervisor): learned {"connection_risk": {"threshold": 80, "escalation": null, "confirmed": false}, "authority_boundary": {"threshold": null, "escalation": null, "confirmed": false}} → checked bag, 1-min connection, lands 0 min before the deadline, cabin upgrade with approval
- `S_fd79a437` (hi, floor 70, margin 45, duty manager): learned {"authority_boundary": {"threshold": null, "escalation": null, "confirmed": false}} → checked bag, 1-min connection, lands 0 min before the deadline, cabin upgrade with approval
- `S_c2714c6c` (fr, floor 65, margin 45, duty manager): learned {"connection_risk": {"threshold": 65, "escalation": null, "confirmed": false}, "authority_boundary": {"threshold": null, "escalation": null, "confirmed": false}} → checked bag, 1-min connection, lands 0 min before the deadline, cabin upgrade with approval
- `S_a7236ef3` (hi, floor 65, margin 15, station supervisor): learned {"authority_boundary": {"threshold": null, "escalation": null, "confirmed": false}} → checked bag, 1-min connection, lands 0 min before the deadline, cabin upgrade with approval
- `S_fe91081d` (fr, floor 85, margin 0, duty manager): learned {"connection_risk": {"threshold": 85, "escalation": null, "confirmed": false}, "authority_boundary": {"threshold": null, "escalation": null, "confirmed": false}} → checked bag, 1-min connection, lands 0 min before the deadline, cabin upgrade with approval
- `S_04deeafd` (hi, floor 60, margin 30, duty manager): learned {"authority_boundary": {"threshold": null, "escalation": null, "confirmed": false}} → checked bag, 1-min connection, lands 0 min before the deadline, cabin upgrade with approval

Unsafe allow = the hidden policy blocks a random booking but the learned rules allow it. Z3-equivalent = proven to block exactly the same bookings as the hidden policy.
