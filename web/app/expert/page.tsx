"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import CaseBoard, { BoardView, emptyView } from "@/components/CaseBoard";
import { AgentHeader, AnswerBox, GateMeter, Line, Transcript } from "@/components/AgentPanel";
import { Alternative, api, Debrief, Question, Rule, Score, Session, Snapshot } from "@/lib/api";
import { apprenticeFirstMessage, apprenticePrompt } from "@/lib/prompts";
import { useTurnGate } from "@/lib/turnGate";
import { useVoiceAgent, VoiceKind, VoiceProvider } from "@/lib/voice";

type Phase = "setup" | "capture" | "debrief" | "done";
type AskStage = "idle" | "asking" | "listening" | "answered";
type LogItem = { ts_label: string; type: string; option?: string | null; score?: Score; asked: boolean; off: boolean };

export default function ExpertPage() {
  return <VoiceProvider><Expert /></VoiceProvider>;
}

const EVENT_FOR: Record<string, string> = {
  inspect: "alternative_inspected", reject: "alternative_rejected", select: "alternative_selected",
  escalate: "escalation_requested", confirm: "rebook_confirmed",
};

function describe(type: string, a?: Alternative) {
  if (!a) return type;
  const verb = { alternative_inspected: "is looking at", alternative_rejected: "ruled out", alternative_selected: "selected",
                 escalation_requested: "asked a supervisor to approve", rebook_confirmed: "confirmed the rebooking on" }[type] ?? type;
  return `Expert ${verb} option ${a.id} (${a.label}: arr ${a.arrival}, ${a.connection_min}-min connection, EUR ${a.price_eur}, ${a.cabin}).`;
}

function Expert() {
  const [health, setHealth] = useState<Record<string, boolean> | null>(null);
  const [kindChoice, setKindChoice] = useState<VoiceKind>("simulated");
  const [expertName, setExpertName] = useState("Claire");
  const [session, setSession] = useState<Session | null>(null);
  const [phase, setPhase] = useState<Phase>("setup");
  const [view, setView] = useState<BoardView>(emptyView());
  const [lines, setLines] = useState<Line[]>([]);
  const [pending, setPending] = useState<Question | null>(null);
  const [awaiting, setAwaiting] = useState<Question | null>(null);
  const [askStage, setAskStageState] = useState<AskStage>("idle");
  const [offRecord, setOffRecord] = useState(false);
  const [maskPii, setMaskPii] = useState(false);
  const [log, setLog] = useState<LogItem[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [debrief, setDebrief] = useState<Debrief | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const sid = useRef<string | null>(null);
  const stage = useRef<AskStage>("idle");
  const offRef = useRef(false);
  const recorded = useRef(false);
  const viewRef = useRef(view);
  viewRef.current = view;
  const phaseRef = useRef(phase);
  phaseRef.current = phase;
  const timers = useRef<number[]>([]);
  const spokenGap = useRef<string | null>(null);
  const spokenTeachback = useRef<string | null>(null);

  const setStage = (s: AskStage) => { stage.current = s; setAskStageState(s); };
  const later = (ms: number, fn: () => void) => { timers.current.push(window.setTimeout(fn, ms)); };
  const clearTimers = () => { timers.current.forEach(clearTimeout); timers.current = []; };

  useEffect(() => {
    api.health().then((h) => { setHealth(h.integrations); if (h.integrations.elevenlabs) setKindChoice("elevenlabs"); })
       .catch(() => setError("Backend not reachable on " + (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000")));
  }, []);

  const addLine = (l: Line) => setLines((prev) => [...prev, l]);
  const refreshRules = useCallback(async () => { if (sid.current) setRules(await api.rules(sid.current)); }, []);
  const refreshDebrief = useCallback(async () => {
    if (!sid.current) return null;
    const d = await api.debrief(sid.current);
    setDebrief(d);
    return d;
  }, []);

  // ------------------------------------------------------------------ voice
  const voice = useVoiceAgent({
    onAgentText: async (text) => {
      if (!sid.current) return;
      const r = await api.transcript(sid.current, "agent", text).catch(() => null);
      addLine({ role: "agent", text, ts_label: r?.ts_label });
    },
    onUserText: async (text) => {
      if (!sid.current) return;
      const r = await api.transcript(sid.current, "user", text, offRef.current).catch(() => null);
      addLine({ role: "user", text: r?.off_record ? "[off the record]" : (r?.text ?? text), ts_label: r?.ts_label,
                redacted: r?.redacted, off: r?.off_record });
      if (phaseRef.current === "capture" && stage.current === "listening") {
        setStage("answered");
        recorded.current = false;
        // Safety net: if the agent forgets to call record_expert_rule, extract server-side.
        later(7000, () => { if (!recorded.current && sid.current && !offRef.current) api.extract(sid.current, text).then(refreshRules).catch(() => {}); });
        later(10000, () => { if (stage.current === "answered") finishAnswer(); });
      }
    },
    onError: (m) => setError(m),
  });

  const finishAnswer = useCallback(() => {
    clearTimers();
    setStage("idle");
    setAwaiting(null);
    voice.setMicOpen(false);
  }, [voice]);

  // EL: mic opens when the agent finishes asking, closes after its short acknowledgement.
  const prevSpeaking = useRef(false);
  useEffect(() => {
    if (voice.kind !== "elevenlabs") return;
    const was = prevSpeaking.current;
    prevSpeaking.current = voice.agentSpeaking;
    if (was && !voice.agentSpeaking) {
      if (stage.current === "asking") { setStage("listening"); voice.setMicOpen(true); later(25000, () => { if (stage.current === "listening") finishAnswer(); }); }
      else if (stage.current === "answered") finishAnswer();
    }
  }, [voice.agentSpeaking, voice, finishAnswer]);

  // In capture the agent mic stays muted except while an answer is expected.
  useEffect(() => {
    if (voice.kind === "elevenlabs" && voice.connected && phase === "capture" && stage.current === "idle") voice.setMicOpen(false);
  }, [voice.connected, voice.kind, phase]); // eslint-disable-line react-hooks/exhaustive-deps

  // ----------------------------------------------------------------- tools
  const tools = {
    get_case_context: async () => (sid.current ? (await api.context(sid.current)).text : "no case"),
    record_expert_rule: async (p: any) => {
      if (offRef.current) return "The expert is off the record. Nothing was stored.";
      recorded.current = true;
      const rule = await api.recordRule({ ...p, session_id: sid.current });
      refreshRules();
      return `Stored: ${rule.title}. ${rule.guardrail ?? ""}`;
    },
    get_debrief_gaps: async () => {
      const d = await refreshDebrief();
      if (d?.gaps[0] && sid.current) api.logQuestion(sid.current, d.gaps[0].question);
      return JSON.stringify({ ready_for_teachback: d?.ready_for_teachback, teachback: d?.teachback,
                              open_gaps: d?.gaps.slice(0, 4).map((g) => ({ gap_id: g.gap_id, question: g.question, mandatory: g.mandatory })) });
    },
    answer_gap: async (p: any) => {
      const r = await api.answerGap({ session_id: sid.current, gap_id: p.gap_id, answer: p.answer ?? p.answer_text ?? "",
                                      threshold_minutes: p.threshold_minutes, escalation: p.escalation, exception: p.exception });
      setDebrief(r.debrief); refreshRules();
      const next = r.debrief.gaps[0];
      if (next && !r.debrief.ready_for_teachback && sid.current) api.logQuestion(sid.current, next.question);
      return JSON.stringify({ ready_for_teachback: r.debrief.ready_for_teachback, teachback: r.debrief.teachback,
                              answered: r.debrief.answered, next_gaps: r.debrief.gaps.slice(0, 3).map((g) => ({ gap_id: g.gap_id, question: g.question, mandatory: g.mandatory })) });
    },
    correct_rule: async (p: any) => {
      const r = await api.correct({ session_id: sid.current, ...p });
      setDebrief(r.debrief); refreshRules();
      return JSON.stringify({ corrected: r.rule.title, guardrail: r.rule.guardrail, teachback: r.debrief.teachback });
    },
    confirm_teachback: async () => {
      if (!sid.current) return "no session";
      const d = await api.confirm(sid.current);
      setDebrief(d); refreshRules(); setPhase("done");
      return "Confirmed. The Work Map is ready.";
    },
    show_evidence: async () => "ok",
  };

  // ------------------------------------------------------------ turn gate
  const gate = useTurnGate({
    enabled: phase === "capture" && !!pending,
    agentSpeaking: voice.agentSpeaking,
    blocked: !!awaiting || offRecord,
  });

  const release = useCallback(async (q: Question) => {
    setPending(null);
    setAwaiting(q);
    setStage("asking");
    await api.asked(q.id).catch(() => null);
    setLog((prev) => prev.map((x) => (x.score?.question === q.text ? { ...x, asked: true } : x)));
    if (voice.kind === "elevenlabs") {
      voice.control("ASK", { question: q.text, category: q.category });
      later(8000, () => { if (stage.current === "asking") { setStage("listening"); voice.setMicOpen(true); } });
    } else {
      await voice.say(q.text);
      setStage("listening");
    }
  }, [voice]);

  useEffect(() => {
    if (gate.gateOpen && pending && !awaiting && phase === "capture" && !offRecord) release(pending);
  }, [gate.gateOpen, pending, awaiting, phase, offRecord, release]);

  // --------------------------------------------------------------- actions
  const start = async () => {
    setStarting(true); setError(null);
    try {
      const s = await api.createSession({ mode: "expert", expert_name: expertName, live: true });
      sid.current = s.session_id;
      setSession(s);
      const v = emptyView();
      setView(v);
      await api.event({ session_id: s.session_id, type: "case_opened", snapshot: snap(s, v) });
      await gate.startVad();
      await voice.start({
        kind: kindChoice, mode: "expert", prompt: apprenticePrompt(expertName), firstMessage: apprenticeFirstMessage(expertName),
        dynamicVariables: { expert_name: expertName }, tools,
      });
      setPhase("capture");
      if (kindChoice === "elevenlabs") {
        const ctx = await api.context(s.session_id);
        later(1200, () => voice.context(`[SCREEN] ${ctx.text}`));
      } else {
        voice.say(apprenticeFirstMessage(expertName));
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStarting(false);
    }
  };

  const snap = (s: Session, v: BoardView): Snapshot => ({
    case_id: s.case.case_id, selected: v.selected, rejected: v.rejected, escalated: v.escalated, focus: v.focus,
    alternatives: s.case.alternatives, flight: s.case.flight, origin: s.case.origin, destination: s.case.destination,
    passenger: { checked_bag: s.case.passenger.checked_bag, arrival_deadline: s.case.passenger.arrival_deadline,
                 original_cabin: s.case.passenger.original_cabin },
  });

  const onAction = async (action: string, id: string) => {
    if (!session || phase !== "capture") return;
    const v = { ...viewRef.current };
    if (action === "inspect") { if (v.focus === id) return; v.focus = id; }
    if (action === "reject") { v.rejected = [...v.rejected, id]; if (v.selected === id) v.selected = null; }
    if (action === "unreject") { v.rejected = v.rejected.filter((x) => x !== id); setView(v); return; }
    if (action === "select") v.selected = id;
    if (action === "escalate") v.escalated = [...v.escalated, id];
    if (action === "confirm") v.confirmed = id;
    setView(v);
    if (action === "escalate") {
      addLine({ role: "system", text: `Approval request sent to duty supervisor for option ${id}.` });
      window.setTimeout(() => {
        setView((cur) => ({ ...cur, approved: [...cur.approved, id] }));
        addLine({ role: "system", text: `Supervisor approved option ${id} (sandbox).` });
      });
    }
    const type = EVENT_FOR[action];
    const alt = session.case.alternatives.find((a) => a.id === id);
    try {
      const r = await api.event({ session_id: session.session_id, type, option_id: id, snapshot: snap(session, v), off_record: offRef.current });
      if (type !== "alternative_inspected" || r.question) {
        setLog((prev) => [{ ts_label: r.ts_label, type, option: id, score: r.score, asked: false, off: r.off_record }, ...prev]);
      }
      if (!r.off_record) voice.context(`[SCREEN] ${describe(type, alt)}`);
      if (r.question) setPending(r.question);
    } catch (e) { setError((e as Error).message); }
  };

  const toggleOffRecord = async () => {
    if (!sid.current) return;
    const on = !offRef.current;
    offRef.current = on;
    setOffRecord(on);
    await api.offRecord(sid.current, on);
    addLine({ role: "system", text: on ? "Off the record: nothing is captured until you resume." : "Back on the record." });
    if (on) { setPending(null); if (stage.current !== "idle") finishAnswer(); }
    voice.context(on ? "[SCREEN] The expert is OFF THE RECORD. Do not record or ask anything." : "[SCREEN] The expert is back on the record.");
  };

  const endTask = async () => {
    if (!sid.current) return;
    clearTimers(); setPending(null); setAwaiting(null); setStage("idle");
    setPhase("debrief");
    const d = await refreshDebrief();
    if (voice.kind === "elevenlabs") {
      voice.setMicOpen(true);
      voice.control("DEBRIEF", { open_gaps: d?.gaps.length ?? 0 });
    }
  };

  // ---------------------------------------------- simulated engine drivers
  const submitCaptureAnswer = async (text: string) => {
    if (!sid.current || !awaiting) return;
    const r = await api.transcript(sid.current, "user", text, offRef.current);
    addLine({ role: "user", text: r.text, ts_label: r.ts_label, redacted: r.redacted });
    setStage("answered");
    try { await api.extract(sid.current, text); } catch {}
    await refreshRules();
    await voice.say("Got it, thank you.");
    finishAnswer();
  };

  useEffect(() => {
    if (voice.kind !== "simulated" || phase !== "debrief" || !debrief || !sid.current) return;
    if (!debrief.ready_for_teachback) {
      const g = debrief.gaps[0];
      if (g && spokenGap.current !== g.gap_id) {
        spokenGap.current = g.gap_id;
        api.logQuestion(sid.current, g.question);
        voice.say(g.question);
      }
    } else if (debrief.teachback && spokenTeachback.current !== debrief.teachback && !debrief.teachback_confirmed) {
      spokenTeachback.current = debrief.teachback;
      voice.say(debrief.teachback);
    }
  }, [debrief, phase, voice]);

  const submitGapAnswer = async (text: string) => {
    if (!sid.current || !debrief?.gaps[0]) return;
    const r = await api.transcript(sid.current, "user", text);
    addLine({ role: "user", text: r.text, ts_label: r.ts_label, redacted: r.redacted });
    const res = await api.answerGap({ session_id: sid.current, gap_id: debrief.gaps[0].gap_id, answer: text });
    setDebrief(res.debrief); refreshRules();
  };

  const submitCorrection = async (text: string) => {
    if (!sid.current) return;
    const r = await api.transcript(sid.current, "user", text);
    addLine({ role: "user", text: r.text, ts_label: r.ts_label, redacted: r.redacted });
    try {
      const res = await api.correct({ session_id: sid.current, text });
      setDebrief(res.debrief); refreshRules();
    } catch (e) { setError((e as Error).message); }
  };

  const confirmTeachback = async () => {
    if (!sid.current) return;
    const r = await api.transcript(sid.current, "user", "Yes, that's how it works.");
    addLine({ role: "user", text: r.text, ts_label: r.ts_label });
    const d = await api.confirm(sid.current);
    setDebrief(d); refreshRules(); setPhase("done");
    if (voice.kind === "simulated") voice.say("Thank you. The Work Map is ready.");
  };

  // poll as a safety net while the voice agent drives the debrief
  useEffect(() => {
    if (phase !== "debrief" || voice.kind !== "elevenlabs") return;
    const id = setInterval(() => { refreshDebrief(); refreshRules(); }, 3000);
    return () => clearInterval(id);
  }, [phase, voice.kind, refreshDebrief, refreshRules]);

  // ------------------------------------------------------------------ render
  if (phase === "setup") {
    return (
      <div className="mx-auto max-w-2xl space-y-5">
        <div>
          <div className="label">Module 1 · Capture</div>
          <h1 className="text-2xl font-bold">Expert session</h1>
          <p className="mt-1 text-mute">The expert handles a live disruption. The apprentice watches the screen as structured events, stays quiet while you talk or work, and asks only at natural pauses.</p>
        </div>
        <div className="card space-y-4 p-5">
          <label className="block">
            <span className="label">Expert name</span>
            <input className="mt-1 w-full rounded-lg border border-line bg-ink px-3 py-2" value={expertName} onChange={(e) => setExpertName(e.target.value)} />
          </label>
          <div>
            <span className="label">Voice engine</span>
            <div className="mt-1 flex gap-2">
              <button className={`btn ${kindChoice === "elevenlabs" ? "btn-primary" : ""}`} disabled={!health?.elevenlabs} onClick={() => setKindChoice("elevenlabs")}>
                ElevenAgents {health && !health.elevenlabs && "(not configured)"}
              </button>
              <button className={`btn ${kindChoice === "simulated" ? "btn-primary" : ""}`} onClick={() => setKindChoice("simulated")}>Simulated (browser voice)</button>
            </div>
          </div>
          <p className="text-xs text-mute">Microphone access is used locally for pause detection. Passenger data is synthetic, and names, PNRs, emails and phone numbers are redacted before anything is stored.</p>
          <button className="btn btn-primary w-full" onClick={start} disabled={starting || !expertName.trim()}>{starting ? "Loading live case…" : "Start live case"}</button>
          {error && <div className="text-sm text-red">{error}</div>}
        </div>
      </div>
    );
  }

  const c = session!.case;
  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]">
      <section className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <div>
            <div className="label">Module 1 · Capture{phase !== "capture" ? " → Module 2 · Debrief" : ""}</div>
            <h1 className="text-xl font-bold">{c.title}</h1>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <label className="flex items-center gap-1.5 text-xs text-mute">
              <input type="checkbox" checked={maskPii} onChange={(e) => setMaskPii(e.target.checked)} /> Mask PII on screen
            </label>
            {phase === "capture" && (
              <>
                <button className={`btn ${offRecord ? "border-amber text-amber" : ""}`} onClick={toggleOffRecord}>
                  {offRecord ? "● Off the record: resume" : "Go off the record"}
                </button>
                <button className="btn btn-primary" onClick={endTask}>End task → Debrief</button>
              </>
            )}
          </div>
        </div>
        <CaseBoard c={c} view={view} onAction={onAction} readOnly={phase !== "capture"} maskName={maskPii} />
        <DecisionLog log={log} />
      </section>

      <aside className="space-y-3">
        <div className="card apprentice-board space-y-4 p-5">
          <AgentHeader kind={voice.kind} connected={voice.connected} speaking={voice.agentSpeaking} title="SkyMentor apprentice" />
          {phase === "capture" && (
            <GateMeter gate={gate} pending={pending?.text ?? null} awaiting={!!awaiting} offRecord={offRecord} micOpen={voice.kind === "simulated" ? askStage === "listening" : voice.micOpen} />
          )}
          {phase === "capture" && voice.kind === "simulated" && askStage === "listening" && (
            <AnswerBox onSubmit={submitCaptureAnswer} placeholder="Answer the apprentice (type or dictate)…" />
          )}
          {phase !== "capture" && debrief && (
            <DebriefPanel d={debrief} kind={voice.kind} phase={phase} onAnswer={submitGapAnswer} onCorrect={submitCorrection}
                          onConfirm={confirmTeachback} sessionId={session!.session_id} />
          )}
          <Transcript lines={lines} />
          {error && <div className="text-xs text-red">{error}</div>}
        </div>
        <RulesPanel rules={rules} />
      </aside>
    </div>
  );
}

function DecisionLog({ log }: { log: LogItem[] }) {
  return (
    <div className="card p-4">
      <div className="mb-2 flex items-center justify-between">
        <span className="label">Decision intelligence · Q = 0.30·novelty + 0.25·importance + 0.25·gap + 0.20·uncertainty</span>
        <span className="text-xs text-mute">threshold 0.60 · max 5 live questions</span>
      </div>
      {log.length === 0 && <div className="text-sm text-mute">Rule out, select or escalate an option. Each action is scored here.</div>}
      <div className="max-h-56 space-y-1.5 overflow-y-auto">
        {log.map((l, i) => (
          <div key={i} className="grid grid-cols-[48px_1fr_60px_1.6fr] items-center gap-2 text-xs">
            <span className="num text-mute">{l.ts_label}</span>
            <span>{l.type.replace("alternative_", "").replace("_", " ")} <b>{l.option}</b></span>
            <span className={`num font-semibold ${l.score?.ask ? "text-amber" : "text-mute"}`}>Q {l.score?.q?.toFixed(2) ?? "–"}</span>
            <span className="truncate text-mute" title={l.score?.reasons?.join("; ")}>
              {l.off ? "off the record" : l.score?.ask ? (l.asked ? "asked at pause" : "queued for pause") : l.score?.reasons?.[0] ?? ""}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function RulesPanel({ rules }: { rules: Rule[] }) {
  return (
    <div className="card p-4">
      <div className="label mb-2">Captured knowledge ({rules.length})</div>
      {rules.length === 0 && <div className="text-sm text-mute">Rules appear here as the expert explains decisions.</div>}
      <div className="space-y-2">
        {rules.map((r) => (
          <div key={r.rule_id} className="fade-in rounded-lg border border-line p-2.5 text-sm">
            <div className="flex items-center gap-2">
              <span className="font-semibold">{r.title}</span>
              <span className={`chip ml-auto ${r.expert_confirmed ? "text-green border-green/40" : "text-amber border-amber/40"}`}>
                {r.expert_confirmed ? "CONFIRMED" : "DRAFT"}
              </span>
            </div>
            <div className="mt-1 text-xs text-mute">{r.guardrail}</div>
            <div className="mt-1 flex gap-3 text-[11px] text-mute">
              <span>conf {(r.confidence * 100).toFixed(0)}%</span>
              {r.source_transcript_span && <span className="num">said {r.source_transcript_span}</span>}
              <span>{r.extracted_by}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function DebriefPanel({ d, kind, phase, onAnswer, onCorrect, onConfirm, sessionId }: {
  d: Debrief; kind: VoiceKind; phase: Phase; onAnswer: (t: string) => void; onCorrect: (t: string) => void;
  onConfirm: () => void; sessionId: string;
}) {
  const [correcting, setCorrecting] = useState(false);
  if (phase === "done" || d.complete) {
    return (
      <div className="rounded-lg border border-green/40 bg-green/5 p-3">
        <div className="font-semibold text-green">Teach-back confirmed · Work Map ready</div>
        <div className="mt-1 text-xs text-mute">{d.answered} follow-ups answered · {d.corrections} correction(s)</div>
        <div className="mt-3 flex gap-2">
          <Link className="btn btn-primary" href={`/workmap/${sessionId}`}>Open Work Map</Link>
          <Link className="btn" href="/trainee">Teach a new hire →</Link>
        </div>
      </div>
    );
  }
  const gap = d.gaps[0];
  return (
    <div className="space-y-2 rounded-lg border border-line bg-ink/60 p-3 text-sm">
      <div className="flex items-center justify-between">
        <span className="label">Debrief</span>
        <span className="text-xs text-mute">{d.answered}/{d.min_questions}+ answered · {d.mandatory_open} mandatory open</span>
      </div>
      {!d.ready_for_teachback && gap && (
        <>
          <div className="rounded border border-amber/40 bg-amber/5 p-2 text-amber">
            {gap.mandatory && <span className="chip mr-2 border-amber/40 text-[9px]">MUST CLOSE</span>}{gap.question}
          </div>
          {kind === "simulated" && <AnswerBox key={gap.gap_id} onSubmit={onAnswer} />}
        </>
      )}
      {d.ready_for_teachback && d.teachback && (
        <>
          <div className="label">Teach-back</div>
          <div className="rounded border border-sky/40 bg-sky/5 p-2">{d.teachback}</div>
          <div className="flex gap-2">
            <button className="btn btn-primary" onClick={onConfirm}>Yes, that's how it works</button>
            {kind === "simulated" && <button className="btn" onClick={() => setCorrecting((x) => !x)}>Correct something</button>}
          </div>
          {correcting && <AnswerBox onSubmit={(t) => { onCorrect(t); setCorrecting(false); }} placeholder='e.g. "Make it 90 minutes at Heathrow"' />}
        </>
      )}
    </div>
  );
}
