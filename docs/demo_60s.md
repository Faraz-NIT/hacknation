# Demo script (60 seconds)

Everything is pre-staged; only one answer is live. For the full walkthrough see
[demo_script.md](demo_script.md).

## Before you start

- Run one complete Capture → Debrief → confirm as "Claire" so the Work Map and Teach have data.
- Open these tabs, left to right:
  1. **Capture**: a new session in French, option A already rejected, agent about to ask
  2. **Debrief**: teach-back visible
  3. **Work Map**: scrolled to *Formal verification*
  4. **Teach**: option A selected, ready to confirm
  5. **Benchmark**
- Use headphones so the agent never hears itself.
- Don't run the benchmark beforehand: it uses up the Cerebras quota (5 requests/minute).
- Record a screen video of the same run as a backup.

## The minute

| Time | Screen | Do | Say |
|---|---|---|---|
| 0:00 | Capture | Point at the case | "An expert rebooks a stranded passenger. SkyMentor watches, stays quiet, and asks *why* only at pauses." |
| 0:08 | Capture | Answer live: *"Jamais en dessous de 80 minutes avec un bagage."* | "It works in French, German or Hindi, and stores the rule in English." |
| 0:18 | Capture, scroll to Market fares | Scroll | "Live fares, weather and flight status give the facts; the expert gives the judgment." |
| 0:24 | Debrief | Point at the teach-back | "Then it asks only about what's missing, and reads back what it learned for the expert to confirm or correct." |
| 0:32 | Work Map | Point at the verification tiles | "Every rule is formally verified by a solver. These are proofs, not guesses." |
| 0:40 | Teach | Click **Confirm** on A: blocked | "A new hire on an unseen case is stopped before saving, in the expert's own words, with the smallest change that would pass." |
| 0:50 | Benchmark | Point at the 100% rows | "Tested against simulated experts with hidden rules in four languages: every rule recovered and proven equivalent." |
| 0:57 | | | "Experts provide the judgment. SkyMentor makes it teachable." |

## If something goes wrong

- **The French answer fails:** say "captured earlier" and move to the next tab.
- **Running long:** cut the Market fares beat (0:18) first. The Teach block is the moment to protect.
- **The agent doesn't ask:** skip straight to the Debrief tab; the prepared session has everything.

Rehearse twice with a timer: tab switching is what eats the time.
