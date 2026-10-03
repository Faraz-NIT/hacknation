# Demo script (about 3 minutes)

Before going on stage: open the home page and click **Reset demo**, then
**Warm live-data cache**. Use headphones so the voice agent never hears itself.

## 0:00 Hook (15 s)
"Process documents capture what people do. They rarely capture why an expert breaks the normal path.
SkyMentor learns that judgment while the work is happening."

## 0:15 Capture (60 s) · Module 1
Open **1 · Capture**, expert name "Claire", start the live case. Narrate as you work: the agent stays quiet.
Point at the **Turn gate** panel, which shows voice level and pause timer.

1. **Rule out A (Doha).** Pause. The agent asks about the 55-minute connection (*guardrail question*).
   Say: "With a checked bag, 55 minutes in Doha is too tight. I never go below 75 minutes."
2. **Rule out C (Helsinki).** Agent: "Helsinki was the cheapest. What made it a no?"
   Say: "It lands at 10:25, after her deadline. She'd miss the signing."
3. **Escalate D (Amsterdam, business only).** Agent asks where your limit is (*guardrail question*).
   Say: "That's an upgrade. I can't approve that myself."
4. **Select B (London) and confirm.** No question here: the **Decision intelligence** log shows
   Q 0.53, below the threshold. That's "ask less, later."
5. Optional: **Go off the record**, say something, and resume. Nothing is stored.

## 1:15 Debrief (40 s) · Module 2
Click **End task → Debrief**. The agent asks at least 3 follow-ups computed from missing fields
(deadline margin, who approves upgrades, exceptions). It then reads the teach-back.
**Correct one detail**: "Make the minimum 80 minutes." Then confirm.

## 1:55 Work Map (20 s)
Open the Work Map: 6 steps, 3 judgment calls, 3 expert-confirmed guardrails. Click a step to see the
screen replay at that timestamp, the question asked, the reason in Claire's words with the transcript
span, and the guardrail with its machine condition. Mention **Export agent-ready guardrails**.

## 2:15 Teach (35 s) · Module 3
A second person opens **3 · Teach** on a case Claire never saw (CDG→JFK).
Tutor asks for a prediction. The trainee picks **A via Reykjavik** (cheapest and earliest,
48-min connection with a bag) and clicks Confirm.
The confirm is **blocked before save**. "Claire would stop here. Why do you think?" The trainee explains, then sees
Claire's own words and her screen replay. They pick Dublin, and the **mastery report** appears.

## 2:50 Close and moonshot (10 s)
"Real-time APIs provide the facts. Experts provide the judgment. ElevenLabs captures the why.
Next: a living operations memory that only asks when something new appears, and exports the same
confirmed guardrails to the agents that will take routine steps."
