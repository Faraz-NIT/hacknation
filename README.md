# SkyMentor Live: AI Apprentice for airline disruption operations

Hack-Nation × ElevenLabs, *The AI Apprentice*. A senior disruption agent rebooks a stranded
passenger while an ElevenLabs voice agent watches the screen as structured events. It stays
quiet while she works and asks *why* at natural pauses. A debrief turns the session into an
evidence-backed **Work Map**. A tutor then coaches a new hire on an unseen case, and a
deterministic guardrail stops a risky confirm **before it is saved**.

```
Capture ─► Map ─► Teach
expert judgment   structured memory   transfer of judgment
```

## Quick start (no keys needed)

Requires Python 3.11+ and Node 20+.

```bash
# terminal 1: API on :8000
cd api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# terminal 2: web on :3000
cd web
npm install
npm run dev
```

Or run `./scripts/dev.sh` for both. Open http://localhost:3000.

Without keys the app uses the **simulated voice**: browser speech synthesis for the agent, and you
type or dictate answers. Every module works end to end, so you can rehearse anywhere.
`SKYMENTOR_OFFLINE=1` also skips all live-data calls.

Run the backend test of the whole loop: `cd api && python -m pytest -q`.

## Turn on the real pieces

| Piece | What to set | Doc |
|---|---|---|
| ElevenLabs voice agent | `ELEVENLABS_AGENT_ID` (+ `ELEVENLABS_API_KEY` for a private agent) in `api/.env` | [docs/elevenlabs_setup.md](docs/elevenlabs_setup.md) |
| LLM rule extraction (backend path) | `CEREBRAS_API_KEY` (optional `CEREBRAS_MODEL`) | falls back to a deterministic extractor |
| Live flight status | `AVIATIONSTACK_KEY` | free plan is HTTP-only / non-commercial |
| Live public fares | `BRIGHTDATA_API_TOKEN`, `BRIGHTDATA_FLIGHTS_DATASET_ID` | adjust the field mapping in `api/app/services/live.py` to your dataset |
| Airport weather | nothing (Open-Meteo) | |

Copy `api/.env.example` → `api/.env` and `web/.env.example` → `web/.env.local`.

Live data is fetched **once** at session start, frozen into the case snapshot, saved raw to
`api/data/cache/`, and labelled `LIVE` or `CACHED HH:MM`. The scenario's alternatives stay fixed by
default so the three hidden rules always appear. Live fares and weather are shown as context.
Set `USE_LIVE_ALTERNATIVES=1` to swap in live itineraries.

## How it answers the Apprentice Test

| Question | Mechanism | Where |
|---|---|---|
| **When to ask** | Local voice-activity detector + typing/click idle ≥ 1.5 s + agent not speaking. During capture the agent's mic is **muted** until a question is released, so it cannot interrupt. | `web/lib/turnGate.ts`, `web/app/expert/page.tsx` |
| **What to ask** | Each UI event is scored: `Q = 0.30·novelty + 0.25·importance + 0.25·alternative_gap + 0.20·uncertainty`, threshold 0.6, budget of 5 live questions. Questions reference the visible trade-off and never ask what the screen already shows. The live log shows *why* each action was or wasn't asked about. | `api/app/engine/scoring.py` |
| **When it has understood** | Gaps come from a validator over typed rules (missing threshold, approver, exception, uncovered category, unseen cases), not from the model's imagination. Debrief is done when no mandatory gap is open, ≥ 3 follow-ups are answered, and the expert confirms the teach-back. Corrections are tracked. | `api/app/engine/debrief.py` |
| **Did the new hire learn** | Unseen case. Prediction first, deterministic block on confirm, explanation scored, expert's words + replayed screen moment, mastery report (mastered / learned with coaching / practise next). | `api/app/engine/tutor.py`, `web/app/trainee/page.tsx` |
| **Trust** | Off-the-record toggle (no questions, no events, no rules; transcript stored as `[off the record]`). Names, PNR, email, phone, card, passport redacted before storage. The app never sends the passenger's name to the agent. Only expert-confirmed rules can block. | `api/app/engine/redact.py`, `api/app/main.py` |

**Design principle:** the agent is conversational, enforcement is deterministic. ElevenLabs owns
listening, asking and teaching. Python owns rule matching and blocking (`api/app/engine/rules.py`).

## Repository

```
api/                      FastAPI + SQLite (JSON columns)
  app/main.py             all endpoints (/api/...)
  app/models.py           Pydantic contracts (Case, LearnedRule, ...)
  app/engine/
    scoring.py            question scorer (when/what to ask)
    extraction.py         answer -> typed rules (LLM or heuristic)
    store.py              rule persistence + provenance (event, transcript span, quote)
    debrief.py            gap validator + teach-back
    rules.py              decision facts + deterministic guardrail evaluator
    workmap.py            Work Map + agent-ready markdown export
    tutor.py              interventions + mastery
    redact.py             PII redaction
  app/services/           live adapters (Bright Data, Aviationstack, Open-Meteo) + case engine
  app/fixtures/           case_A (expert, CDG→HND) and case_B (trainee, CDG→JFK)
  tests/test_flow.py      full Capture→Map→Teach loop
web/                      Next.js + Tailwind
  app/expert              Capture + debrief
  app/workmap             clickable Work Map with screen replays
  app/trainee             Teach mode, guardrail block, mastery
  lib/voice.tsx           ElevenAgents engine + simulated engine behind one interface
  lib/turnGate.ts         pause detection
  lib/prompts.ts          interviewer + tutor system prompts
docs/                     ElevenLabs setup, demo script
```

## The scenario

**Case A (expert):** LH716 FRA→HND cancelled. The passenger has a checked bag, must land in Tokyo by 10:00,
and holds an economy ticket. Options:
- A, via Doha: earliest, 55-min connection
- B, via London: 105-min connection
- C, via Helsinki: cheapest, lands 10:25
- D, via Amsterdam: business only

Hidden rules: minimum connection with a bag, protect the deadline, and a cabin change needs approval.

**Case B (trainee, never shown to the expert):** CDG→JFK.
- A, via Reykjavik: cheapest and earliest, with a **48-min connection** and a checked bag
- C, via London: lands after the deadline
- D, nonstop: premium economy only
- B, via Dublin: the correct choice

## Known limits and next steps

- Screen understanding uses structured DOM events from the sandbox UI, not a vision model. The event
  contract is source-agnostic, so a frame-diff vision path can feed the same `/api/events`.
- Bright Data dataset schemas vary; check the normaliser against your dataset.
- Redaction is regex-based; swap in Microsoft Presidio for broader coverage.
- Stretch goals that are cheap from here: German capture → English tutor (agent language override),
  MCP tool for the tutor to query guardrails.
