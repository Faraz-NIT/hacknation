# ElevenLabs setup (about 15 minutes)

SkyMentor runs without ElevenLabs (simulated browser voice). To use the real
voice agent, create **one** ElevenAgents agent and configure it as below. The
app sends the interviewer or tutor prompt as a per-session override, so one
agent covers both roles.

> Dashboard labels move around between releases. If a setting below has a
> slightly different name in your dashboard, look for the equivalent.

## 1. Create the agent

- **ElevenAgents → Create agent → Blank**
- **First message:** anything (it is overridden per session)
- **System prompt:** paste the *apprentice* prompt from `web/lib/prompts.ts` (used if overrides are off)
- **LLM:** a strong tool-calling model (the brief suggests choosing the model behind the agent; tool use must be reliable)
- **Voice:** a calm, curious voice. Turn on Expressive Mode if available.
- **Turn taking:** set eagerness to the most *patient* setting. The app also mutes the mic during capture, so the agent cannot interrupt even if this is left at default.
- **System tools (optional):** enable *skip turn* so the agent can stay silent when the expert narrates.

## 2. Allow overrides

**Agent → Security → Overrides:** enable **System prompt**, **First message** and **Language**
(Language is needed for French, German or Hindi capture; the voice model must be multilingual).

If you can't or don't want to enable overrides, set `NEXT_PUBLIC_EL_USE_OVERRIDES=0` in
`web/.env.local`, create a second agent with the *tutor* prompt, and set
`ELEVENLABS_AGENT_ID_EXPERT` / `ELEVENLABS_AGENT_ID_TRAINEE` in `api/.env`.

## 3. Authentication

- **Public agent:** set only `ELEVENLABS_AGENT_ID` in `api/.env`.
- **Private agent (recommended):** turn on authentication and also set `ELEVENLABS_API_KEY`.
  The backend mints a signed URL (`GET /api/elevenlabs/session`), so the key never reaches the browser.

## 4. Client tools

Add each tool as **Tools → Add tool → Client tool**, with **Wait for response** turned ON.
The browser implements them; they call the FastAPI backend. Names must match exactly.

### Interviewer / debrief tools

| Name | Parameters | Purpose |
|---|---|---|
| `get_case_context` | none | PII-free case summary |
| `record_expert_rule` | `decision_type` string (required; one of `connection_risk`, `customer_deadline`, `authority_boundary`, `other`), `reason` string (required), `threshold_minutes` number, `escalation` string, `exception` string, `quote` string | Store a typed rule after each answer |
| `get_debrief_gaps` | none | Open gaps computed from missing rule fields |
| `answer_gap` | `gap_id` string (required), `answer` string (required), `threshold_minutes` number, `escalation` string, `exception` string | Close one gap; returns the next gaps or the teach-back |
| `correct_rule` | `text` string (required), `decision_type` string, `threshold_minutes` number, `escalation` string, `exception` string | Apply a correction during teach-back |
| `confirm_teachback` | none | Expert confirmed: rules become enforceable |

### Tutor tools

| Name | Parameters | Purpose |
|---|---|---|
| `get_case_context` | none | Trainee case summary |
| `get_expert_rules` | none | The expert's confirmed rules and quotes |
| `record_prediction` | `text` string (required) | Trainee's up-front prediction |
| `record_explanation` | `text` string (required), `rule_id` string | Trainee's explanation after a block |
| `show_evidence` | `rule_id` string | Reveals the expert's quote and screen replay |
| `check_guardrail` | `option_id` string (required), `connection_min` number, `arrival` string (HH:MM), `cabin` string, `checked_bag` boolean, `has_supervisor_approval` boolean | "What if" check: runs the expert's guardrails on a hypothetical option. Read-only |

Parameter descriptions for the dashboard can be short, e.g. for `threshold_minutes`:
*"Number the expert stated, e.g. minimum connection minutes or deadline margin. Omit if not stated."*

## 5. How the app talks to the agent

- **Screen events** go to the agent as `sendContextualUpdate("[SCREEN] Expert ruled out option A ...")`. These never trigger speech.
- **Questions** are released by the app's turn gate, not by the LLM:
  `sendUserMessage("[CONTROL:ASK] question=...")`. The prompt tells the agent to say it and listen.
- **Mic gating:** during capture the agent mic is muted, opened only after the question is spoken,
  and muted again after the agent's short acknowledgement.
- **Debrief / tutor:** `[CONTROL:DEBRIEF]`, `[CONTROL:START]`, `[CONTROL:BLOCK] script=... reveal=...`, `[CONTROL:FINISHED] summary=...`.

## 6. Test checklist

1. Home page shows `● elevenlabs`.
2. Capture → pick *ElevenAgents* → Start. You hear the greeting.
3. Talk while you rule out option A: the agent stays silent. Stop talking and let go of the mouse: within ~2 s it asks about the 55-minute connection.
4. Answer. The rule appears in *Captured knowledge* (if the agent forgets the tool call, the backend extracts it after 7 s).
5. End task → the agent runs the debrief and teach-back from the tool results.
