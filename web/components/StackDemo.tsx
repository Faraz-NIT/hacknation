"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import SkyBuddy from "@/components/SkyBuddy";

const NODES = [
  { id: "sources", label: "The facts", tech: "Aviationstack · Open-Meteo · Google Flights", mark: "↗", detail: "Aviationstack supplies flight status and Open-Meteo supplies weather. Configured Bright Data supplies fares; otherwise fast-flights builds a Google Flights query and primp fetches the public results. Python normalizes and caches the response, freezes the session snapshot, and displays market fares as context alongside the scenario options.", sample: "flight status + weather + public market fares\nBright Data configured? use it : Google Flights\n→ frozen case snapshot + live/cache provenance" },
  { id: "interface", label: "The workspace", tech: "Next.js · React · Tailwind", mark: "⌘", detail: "The browser renders alternatives and emits structured inspect, reject, select, and confirm events. Local speech and activity detection decides when it is safe to ask a queued question.", sample: 'event: alternative_rejected\noption: A · connection: 55 min · checked bag: yes' },
  { id: "voice", label: "The conversation", tech: "ElevenLabs · WebSocket", mark: "≋", detail: "ElevenAgents asks and listens through the React SDK. Client tools send expert rules back to Python. A muted agent microphone and the local turn gate keep capture questions from interrupting work.", sample: "Why did you rule out the earliest arrival?" },
  { id: "extraction", label: "The learning", tech: "Cerebras · LLM extraction", mark: "✦", detail: "Cerebras is the optional backend extraction path for simulated answers and backfill, including multilingual answers normalized into English rules with original-language quotes. In live voice mode, the ElevenLabs agent can record a typed rule directly through its client tool. Python validates both paths; the deterministic fallback extractor is English-only.", sample: 'decision_type: connection_risk\nthreshold_min: 75\nexpert_confirmed: false' },
  { id: "api", label: "The orchestration", tech: "Python · FastAPI · Pydantic", mark: "{ }", detail: "FastAPI scores visible decisions, manages sessions and debriefs, redacts passenger data, and validates rule contracts. It owns state and enforcement; the voice model owns conversation.", sample: "Q = .30 novelty + .25 importance\n  + .25 alternative gap + .20 uncertainty" },
  { id: "memory", label: "The evidence", tech: "SQLite · Work Map", mark: "▤", detail: "SQLite stores structured rules alongside the screen event, timestamp, expert quote, and corrections. The Work Map connects each decision to its reasoning. Only expert-confirmed rules can block.", sample: 'rule → event → transcript span → expert quote\nstatus: expert-confirmed' },
  { id: "guardrails", label: "The safety net", tech: "Python rules · Z3 verification", mark: "✓", detail: "Python compares the trainee's itinerary against confirmed rules and blocks a risky confirm before saving. Z3 mirrors the rule semantics as SMT constraints to check consistency and equivalence, and find minimal counterfactual changes. The What-if panel evaluates hypothetical bookings without storing them.", sample: 'checked_bag && connection_min < 75\n→ Python blocks confirm\n→ Z3: connection ≥ 75 min or carry-on only' },
] as const;

type NodeId = typeof NODES[number]["id"];
const STAGES: { label: string; title: string; text: string; quote: string; speaker: string; nodes: NodeId[]; path: string; payload: string; outcome: string }[] = [
  { label: "Load the facts", title: "Normalize the external context.", text: "Python combines Aviationstack flight status, Open-Meteo weather, and public fares from Google Flights via fast-flights, or configured Bright Data. Results are cached and frozen at session start. Market fares are displayed as context alongside the fixed scenario options.", quote: "Same facts for every decision. Public fares stay separate from the scenario.", speaker: "SKY / CONTEXT", nodes: ["sources", "api", "interface"], path: "M150 60 H300 V210 H450 V60", payload: "Provider response → normalized data → cache → case snapshot", outcome: "Scenario options plus provenance-labelled market context" },
  { label: "Watch the decision", title: "An action becomes an event.", text: "The expert rules out the earliest option. React sends a structured event to FastAPI, including the alternative and the visible screen state.", quote: "You passed over the earliest arrival. There’s a reason here.", speaker: "SKY / OBSERVING", nodes: ["interface", "api"], path: "M450 60 V210", payload: "alternative_rejected · A · 55-minute connection", outcome: "Expert behavior captured with screen context" },
  { label: "Find the right pause", title: "A good question needs good timing.", text: "Python scores the trade-off. The browser waits for at least 1.5 seconds of speech and activity idle before releasing the question, while respecting off-the-record mode.", quote: "I’ve got a question. I’ll wait until you’re ready.", speaker: "SKY / WAITING", nodes: ["api", "interface"], path: "M450 210 V60", payload: "Worth asking? Q ≥ 0.6 · safe pause? ≥ 1.5 s", outcome: "A queued question released at a natural pause" },
  { label: "Ask the expert", title: "Voice uncovers the why.", text: "ElevenLabs asks about the visible trade-off. The expert explains the hidden constraint in their own words, rather than filling in a rule form.", quote: "With a checked bag, I never go below a 75-minute connection.", speaker: "EXPERT / THE REASON", nodes: ["interface", "voice", "api"], path: "M450 60 H750 M750 60 H600 V210 H450", payload: "Spoken answer → transcript + client tool", outcome: "Judgment expressed in the expert’s own words" },
  { label: "Extract the rule", title: "A sentence becomes structured knowledge.", text: "The live agent can record a typed rule through its tool. Cerebras handles optional backend extraction and backfill. Pydantic validates the proposal before storage.", quote: "Got it: checked bags need at least 75 minutes. Still a draft.", speaker: "SKY / LEARNING", nodes: ["voice", "api", "extraction", "memory"], path: "M750 60 V210 H150 M150 210 H750", payload: "connection_risk · minimum 75 min · unconfirmed", outcome: "A validated rule proposal, with its source evidence" },
  { label: "Confirm the memory", title: "The expert gets the final word.", text: "A debrief closes missing thresholds, approvals, and exceptions. The expert confirms the teach-back. SQLite preserves the rules and evidence in a clickable Work Map.", quote: "You’ve checked my understanding. This can now teach someone else.", speaker: "SKY / REMEMBERING", nodes: ["interface", "api", "memory"], path: "M450 60 V210 H750", payload: "Teach-back confirmed → rule + quote + screen event", outcome: "An expert-confirmed playbook the team can reuse" },
  { label: "Coach the next person", title: "Enforce, verify, and explain.", text: "Python blocks a 48-minute connection against a confirmed 75-minute minimum. Z3 mirrors the guardrails as SMT constraints, checks consistency and equivalence, and computes minimal changes that would pass. ElevenLabs explains using the expert’s quote and event evidence.", quote: "Claire would stop here. What would need to change for this option to pass?", speaker: "SKY / COACHING", nodes: ["interface", "memory", "api", "guardrails", "voice"], path: "M750 210 H450 V360 M450 360 V60 H750", payload: "Python: block confirm · Z3: minimal safe counterfactual", outcome: "Deterministic enforcement with evidence and what-if reasoning" },
];

const DIAGRAM_SCRIPT = "Across the top, Aviationstack provides flight status, Open-Meteo weather, and Google Flights fares through fast-flights, with Bright Data used when configured. Next.js, React, and Tailwind render the workspace and emit structured events. ElevenLabs handles voice over WebSocket and invokes client tools. On the second row, Cerebras provides optional backend extraction into typed rules; FastAPI scores events, manages sessions, redacts data, and validates contracts with Pydantic. SQLite stores rules, transcripts, and event provenance for the Work Map. At the bottom, Python enforces confirmed guardrails, while Z3 checks consistency and equivalence and computes minimal counterfactual changes.";

const CONNECTIONS = ["M150 60 H300 V210 H450", "M450 60 H750", "M450 60 V210", "M750 60 H600 V210 H450", "M150 210 H750", "M450 210 V360"];

export default function StackDemo() {
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [selected, setSelected] = useState<NodeId | null>(null);
  const timeline = useRef<HTMLOListElement>(null);
  const stage = STAGES[step];
  const detail = NODES.find((node) => node.id === selected);

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => { setReducedMotion(media.matches); if (media.matches) setPlaying(false); };
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (!playing || reducedMotion) return;
    const timer = window.setTimeout(() => {
      if (step === STAGES.length - 1) setPlaying(false);
      else { setStep(step + 1); setSelected(null); }
    }, 7000 / speed);
    return () => window.clearTimeout(timer);
  }, [playing, reducedMotion, step, speed]);

  useEffect(() => {
    const list = timeline.current;
    const active = list?.querySelector<HTMLElement>('[aria-current="step"]');
    if (!list || !active || list.scrollWidth <= list.clientWidth) return;
    const left = active.getBoundingClientRect().left - list.getBoundingClientRect().left + list.scrollLeft;
    list.scrollTo({ left: Math.max(0, left - list.clientWidth / 2 + active.clientWidth / 2), behavior: reducedMotion ? "instant" : "smooth" });
  }, [step, reducedMotion]);

  const jump = (index: number) => { setStep(index); setPlaying(false); setSelected(null); };
  const play = () => {
    if (playing) { setPlaying(false); return; }
    if (step === STAGES.length - 1) { setStep(0); setSelected(null); }
    setPlaying(true);
  };

  return <div className="stack-demo space-y-6" data-running={playing}>
    <header className="stack-heading">
      <div><div className="label text-sky">Inside SkyMentor / interactive stack tour</div><h1 className="mt-2 text-4xl uppercase sm:text-5xl">One decision. <span className="text-sky">Seven moving parts.</span></h1><p className="mt-3 max-w-2xl text-sm text-mute">Follow the journey from an expert’s instinct to a new hire’s next move. Select a component to look under the hood.</p></div>
      <Link href="/expert" className="btn">Try the workspace ↗</Link>
    </header>

    <section className="stack-console" aria-label="Animated technology walkthrough">
      <div className="stack-console-top"><span className="stack-example-badge">Illustrated walkthrough</span><span>Capture → Map → Teach</span></div>
      <div className="stack-main">
        <div className="stack-network" aria-label="Technology components">
          <svg className="stack-wires" viewBox="0 0 900 420" preserveAspectRatio="none" aria-hidden="true">
            {CONNECTIONS.map((path) => <path key={path} d={path} />)}
            <path key={step} className="stack-signal" d={stage.path} />
          </svg>
          {NODES.map((node) => <button key={node.id} type="button" className="stack-node" data-node={node.id} data-active={stage.nodes.includes(node.id)} aria-pressed={selected === node.id} onClick={() => { setSelected(selected === node.id ? null : node.id); setPlaying(false); }}>
            <span className="stack-node-mark" aria-hidden="true">{node.mark}</span><span className="stack-node-label">{node.label}</span><span className="stack-node-tech">{node.tech}</span>
            <span className="stack-node-state">{stage.nodes.includes(node.id) ? "In this step" : "Explore component"}</span>
          </button>)}
        </div>

        <div className="stack-narrative" aria-live={playing ? "off" : "polite"} aria-atomic="true">
          <div className="stack-chapter">0{step + 1} / 0{STAGES.length}<span>{stage.label}</span></div>
          <div key={step} className="fade-in"><h2>{stage.title}</h2><p className="stack-story">{stage.text}</p></div>
          <div className="stack-speech"><SkyBuddy className="stack-buddy" mood={playing && step === 3 ? "speaking" : playing ? "listening" : "ready"} /><div><span>{stage.speaker}</span><p key={stage.quote} className="fade-in">“{stage.quote}”</p></div></div>
          <div className="stack-payload"><span>What moves through the system</span><p key={stage.payload} className="fade-in">{stage.payload}</p></div>
          <div className="stack-outcome"><span aria-hidden="true">✓</span>{stage.outcome}</div>
        </div>
      </div>

      <div className="stack-playback">
        <div className="stack-controls">
          <button type="button" className="btn btn-primary" onClick={play} disabled={reducedMotion}>{playing ? "Ⅱ Pause tour" : step === STAGES.length - 1 ? "↺ Replay tour" : "▶ Play tour"}</button>
          <button type="button" className="btn" onClick={() => jump(0)} aria-label="Restart tour">↺</button>
          <button type="button" className="btn" disabled={step === 0} onClick={() => jump(step - 1)} aria-label="Previous step">←</button>
          <button type="button" className="btn" disabled={step === STAGES.length - 1} onClick={() => jump(step + 1)} aria-label="Next step">→</button>
          <label className="stack-speed">Speed<select value={speed} onChange={(event) => setSpeed(Number(event.target.value))}><option value={1}>1×</option><option value={2}>2×</option></select></label>
        </div>
        <span className="stack-timing">{reducedMotion ? "Reduced motion enabled · use the step controls" : `${49 / speed}-second tour · no microphone needed`}</span>
      </div>
      <ol ref={timeline} className="stack-timeline" aria-label="Tour chapters">
        {STAGES.map((item, index) => <li key={item.label}><button type="button" onClick={() => jump(index)} aria-current={step === index ? "step" : undefined} data-complete={index < step}><span>0{index + 1}</span>{item.label}</button></li>)}
      </ol>
    </section>

    {detail ? <section className="card stack-inspector fade-in" aria-label="Component details"><div><span className="label text-sky">Under the hood</span><h2 className="mt-2 text-2xl uppercase">{detail.tech}</h2><p className="mt-2 text-sm text-mute">{detail.detail}</p></div><pre><code>{detail.sample}</code></pre><button type="button" className="btn" onClick={() => setSelected(null)} aria-label="Close component details">Close ×</button></section> : <div className="stack-principles"><span><b>Voice</b> asks and teaches</span><span><b>Python</b> validates and enforces</span><span><b>The expert</b> confirms what is learned</span></div>}
    <div className="card flex flex-wrap items-center gap-4 p-5"><div className="flex-1"><span className="label text-sky">Beyond the walkthrough</span><p className="mt-1 text-sm">Multilingual capture, what-if checks, and a benchmark of expert-rule extraction.</p></div><Link href="/benchmark" className="btn">Explore the benchmark ↗</Link></div>
    <details className="card p-5"><summary className="cursor-pointer font-mono text-xs uppercase">Technical narration · diagram order</summary><p className="mt-4 max-w-4xl text-sm leading-relaxed text-mute">{DIAGRAM_SCRIPT}</p></details>
    <p className="text-xs text-mute">This tour illustrates the architecture with example events and quotes. It does not call providers or create a session. Live voice uses ElevenLabs tools; Cerebras is the optional backend extraction path.</p>
  </div>;
}
