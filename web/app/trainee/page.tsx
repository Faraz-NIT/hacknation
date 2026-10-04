"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import CaseBoard, { BoardView, emptyView } from "@/components/CaseBoard";
import { AgentHeader, AnswerBox, Line, Transcript } from "@/components/AgentPanel";
import { api, Case, Counterfactual, Intervention, Session, WhatIfQuery, WhatIfResult } from "@/lib/api";
import { LANGUAGES, LangCode } from "@/lib/languages";
import { tutorFirstMessage, tutorPrompt } from "@/lib/prompts";
import { useVoiceAgent, VoiceKind, VoiceProvider } from "@/lib/voice";

export default function TraineePage() {
  return <VoiceProvider><Trainee /></VoiceProvider>;
}

type Block = { violations: Intervention[]; stage: "explain" | "revealed"; feedback?: string; counterfactuals: Counterfactual[] };
type WhatIf = { query: WhatIfQuery; result: WhatIfResult; source: "tutor" | "you" };

const num = (v: unknown) => (v === null || v === undefined || v === "" || isNaN(Number(v)) ? undefined : Number(v));
const bool = (v: unknown) => (v === null || v === undefined || v === "" ? undefined : v === true || v === "true");

/** Normalise loosely-typed tool params from the agent into a what-if query. */
function toQuery(p: any): WhatIfQuery {
  return {
    option_id: String(p.option_id ?? "").trim().toUpperCase(),
    connection_min: num(p.connection_min ?? p.connection_minutes),
    arrival: p.arrival ? String(p.arrival) : undefined,
    cabin: p.cabin ? String(p.cabin).toLowerCase().replace(/\s+/g, "_") : undefined,
    checked_bag: bool(p.checked_bag),
    has_supervisor_approval: bool(p.has_supervisor_approval) ?? false,
  };
}

function Trainee() {
  const [health, setHealth] = useState<Record<string, boolean> | null>(null);
  const [kindChoice, setKindChoice] = useState<VoiceKind>("simulated");
  const [session, setSession] = useState<Session | null>(null);
  const [view, setView] = useState<BoardView>(emptyView());
  const [lines, setLines] = useState<Line[]>([]);
  const [predicting, setPredicting] = useState(false);
  const [block, setBlock] = useState<Block | null>(null);
  const [warning, setWarning] = useState<Intervention | null>(null);
  const [mastery, setMastery] = useState<any>(null);
  const [whatIf, setWhatIf] = useState<WhatIf | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const sid = useRef<string | null>(null);
  const blockRef = useRef<Block | null>(null);
  blockRef.current = block;
  const expertName = (session?.state?.expert_name as string) || "the expert";
  const expertLang = ((session?.state?.expert_language as LangCode) || "en");
  const startedTutor = useRef(false);

  useEffect(() => {
    api.health().then((h) => { setHealth(h.integrations); if (h.integrations.elevenlabs) setKindChoice("elevenlabs"); })
       .catch(() => setError("Backend not reachable"));
  }, []);

  const addLine = (l: Line) => setLines((p) => [...p, l]);

  const voice = useVoiceAgent({
    onAgentText: async (text) => {
      if (!sid.current) return;
      const r = await api.transcript(sid.current, "agent", text).catch(() => null);
      addLine({ role: "agent", text, ts_label: r?.ts_label });
    },
    onUserText: async (text) => {
      if (!sid.current) return;
      const r = await api.transcript(sid.current, "user", text).catch(() => null);
      addLine({ role: "user", text: r?.text ?? text, ts_label: r?.ts_label, redacted: r?.redacted });
    },
    onError: (m) => setError(m),
  });

  const tools = {
    get_case_context: async () => (sid.current ? (await api.context(sid.current)).text : "no case"),
    get_expert_rules: async () => (sid.current ? (await api.context(sid.current)).rules_text ?? "none" : "none"),
    record_prediction: async (p: any) => {
      if (!sid.current) return "no session";
      const r = await api.traineeAnswer({ session_id: sid.current, kind: "prediction", text: p.text ?? p.prediction ?? "" });
      return JSON.stringify({ matched_expert_rule: r.correct });
    },
    record_explanation: async (p: any) => {
      if (!sid.current) return "no session";
      const r = await api.traineeAnswer({ session_id: sid.current, kind: "explanation", text: p.text ?? "", rule_id: p.rule_id ?? blockRef.current?.violations[0]?.rule_id });
      setBlock((b) => (b ? { ...b, stage: "revealed", feedback: r.feedback } : b));
      return JSON.stringify({ correct: r.correct, feedback: r.feedback });
    },
    show_evidence: async () => { setBlock((b) => (b ? { ...b, stage: "revealed" } : b)); return "evidence shown"; },
    check_guardrail: async (p: any) => {
      if (!sid.current) return "no session";
      const r = await runWhatIf(toQuery(p), "tutor");
      return JSON.stringify({ allowed: r.allowed, changed: r.changed,
                              blocked_by: r.violations.map((v) => ({ title: v.title, why: v.why, guardrail: v.guardrail })),
                              draft_warnings: r.draft_warnings.map((v) => v.title),
                              would_pass_if: r.would_pass_if.map((cf) => cf.text) });
    },
  };

  const runWhatIf = async (query: WhatIfQuery, source: WhatIf["source"]) => {
    const result = await api.whatIf({ ...query, session_id: sid.current! });
    setWhatIf({ query, result, source });
    const changes = Object.entries(result.changed).map(([k, v]) => `${k.replace("_", " ")} ${v}`).join(", ") || "as is";
    addLine({ role: "system", text: `What-if on option ${query.option_id} (${changes}): ${result.allowed ? "allowed" : "blocked by " + result.violations.map((v) => v.title).join(", ")}` });
    return result;
  };

  // EL: once the greeting finishes, kick off the prediction question.
  const prevSpeaking = useRef(false);
  useEffect(() => {
    const was = prevSpeaking.current;
    prevSpeaking.current = voice.agentSpeaking;
    if (voice.kind === "elevenlabs" && was && !voice.agentSpeaking && !startedTutor.current) {
      startedTutor.current = true;
      voice.control("START");
    }
  }, [voice.agentSpeaking, voice]);

  const predictionQ = () => `Before you pick, which option do you think ${expertName} would rule out first, and why?`;

  const start = async () => {
    setStarting(true); setError(null);
    try {
      const s = await api.createSession({ mode: "trainee", live: true });
      if (!s.expert_session_id) throw new Error("No expert session yet. Run Module 1 (Capture) first.");
      sid.current = s.session_id;
      setSession(s);
      const name = (s.state.expert_name as string) || "the expert";
      const taughtIn = ((s.state.expert_language as LangCode) || "en");
      await voice.start({ kind: kindChoice, mode: "trainee", prompt: tutorPrompt(name, taughtIn), firstMessage: tutorFirstMessage(name),
                          dynamicVariables: { expert_name: name }, tools });
      const ctx = await api.context(s.session_id);
      if (kindChoice === "elevenlabs") {
        voice.setMicOpen(true);
        setTimeout(() => { voice.context(`[SCREEN] ${ctx.text}`); voice.context(`[RULES] ${ctx.rules_text ?? "none"}`); }, 800);
        setTimeout(() => { if (!startedTutor.current) { startedTutor.current = true; voice.control("START"); } }, 9000);
      } else {
        await voice.say(tutorFirstMessage(name));
        await voice.say(predictionQ());
        setPredicting(true);
      }
    } catch (e) { setError((e as Error).message); } finally { setStarting(false); }
  };

  const submitPrediction = async (text: string) => {
    if (!sid.current) return;
    const r = await api.transcript(sid.current, "user", text);
    addLine({ role: "user", text: r.text, ts_label: r.ts_label, redacted: r.redacted });
    const res = await api.traineeAnswer({ session_id: sid.current, kind: "prediction", text });
    setPredicting(false);
    await voice.say(res.correct ? "Good instinct. Keep that in mind as you work." : "Interesting. Let's see how the case plays out.");
  };

  const onAction = async (action: string, id: string) => {
    if (!session || mastery) return;
    const v = { ...view };
    if (action === "inspect") { v.focus = id; setView(v); return; }
    if (action === "reject") { v.rejected = [...v.rejected, id]; if (v.selected === id) v.selected = null; }
    if (action === "unreject") v.rejected = v.rejected.filter((x) => x !== id);
    if (action === "select") v.selected = id;
    if (action === "escalate") {
      v.escalated = [...v.escalated, id];
      addLine({ role: "system", text: `Approval request sent to duty supervisor for option ${id}.` });
      setTimeout(() => {
        setView((cur) => ({ ...cur, approved: [...cur.approved, id] }));
        addLine({ role: "system", text: `Supervisor approved option ${id} (sandbox).` });
      }, 2500);
    }
    setView(v);
    if (action !== "confirm") {
      api.event({ session_id: session.session_id, type: action === "reject" ? "alternative_rejected" : action === "escalate" ? "escalation_requested" : "alternative_selected", option_id: id }).catch(() => {});
      return;
    }
    // Confirm: deterministic guardrail check BEFORE anything is committed.
    const r = await api.evaluate({ session_id: session.session_id, option_id: id, type: "confirm", has_supervisor_approval: v.approved.includes(id) });
    if (!r.allowed) {
      const b: Block = { violations: r.violations, stage: "explain", counterfactuals: r.counterfactuals };
      setBlock(b);
      addLine({ role: "system", text: `Confirm blocked before save: ${r.violations.map((x) => x.title).join(", ")}` });
      const first = r.violations[0];
      if (voice.kind === "elevenlabs") {
        voice.control("BLOCK", { rule_id: first.rule_id, script: first.tutor_script, reveal: first.reveal_script, why: first.why,
                                 would_pass_if: r.counterfactuals.map((cf) => cf.text) });
      } else {
        await voice.say(first.tutor_script);
      }
      return;
    }
    if (r.warnings[0]) setWarning(r.warnings[0]);
    setView({ ...v, confirmed: id });
    api.event({ session_id: session.session_id, type: "rebook_confirmed", option_id: id }).catch(() => {});
    const m = await api.mastery(session.session_id);
    setMastery(m);
    if (voice.kind === "elevenlabs") voice.control("FINISHED", { summary: m.summary, practice_next: m.practice_next });
    else voice.say(`Rebooked. ${m.summary}`);
  };

  const submitExplanation = async (text: string) => {
    if (!sid.current || !block) return;
    const r = await api.transcript(sid.current, "user", text);
    addLine({ role: "user", text: r.text, ts_label: r.ts_label, redacted: r.redacted });
    const res = await api.traineeAnswer({ session_id: sid.current, kind: "explanation", text, rule_id: block.violations[0].rule_id });
    setBlock({ ...block, stage: "revealed", feedback: res.feedback });
    await voice.say(`${res.correct ? "Exactly." : "Not quite."} ${block.violations[0].reveal_script}`);
  };

  const closeBlock = () => {
    setBlock(null);
    setView((v) => ({ ...v, selected: null }));
  };

  if (!session) {
    return (
      <div className="mx-auto max-w-2xl space-y-5">
        <div>
          <div className="label">Module 3 · Teach</div>
          <h1 className="text-2xl font-bold">New-hire session</h1>
          <p className="mt-1 text-mute">A new hire works a case the expert never showed. The tutor asks them to predict, stays quiet while they work and steps in before a guardrail is broken, in the expert's own words.</p>
        </div>
        <div className="card space-y-4 p-5">
          <div>
            <span className="label">Voice engine</span>
            <div className="mt-1 flex gap-2">
              <button className={`btn ${kindChoice === "elevenlabs" ? "btn-primary" : ""}`} disabled={!health?.elevenlabs} onClick={() => setKindChoice("elevenlabs")}>ElevenAgents tutor</button>
              <button className={`btn ${kindChoice === "simulated" ? "btn-primary" : ""}`} onClick={() => setKindChoice("simulated")}>Simulated (browser voice)</button>
            </div>
          </div>
          <button className="btn btn-primary w-full" onClick={start} disabled={starting}>{starting ? "Loading case…" : "Start new-hire case"}</button>
          {error && <div className="text-sm text-red">{error} {error.includes("Capture") && <Link className="underline" href="/expert">Go to Capture</Link>}</div>}
        </div>
      </div>
    );
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_400px]">
      <section className="space-y-3">
        <div>
          <div className="label">Module 3 · Teach · unseen case</div>
          <h1 className="text-xl font-bold">{session.case.title}</h1>
        </div>
        <CaseBoard c={session.case} view={view} onAction={onAction} readOnly={!!mastery} />
        {warning && (
          <div className="card border-amber/40 p-3 text-sm text-amber">Draft rule (not yet confirmed by {expertName}): {warning.why}</div>
        )}
        {mastery && <MasteryCard m={mastery} expertName={expertName} />}
      </section>
      <aside className="space-y-3">
        <div className="card apprentice-board space-y-3 p-5">
          <AgentHeader kind={voice.kind} connected={voice.connected} speaking={voice.agentSpeaking} title={`Tutor · taught by ${expertName}`} accent="violet" />
          {predicting && voice.kind === "simulated" && (
            <div className="space-y-2">
              <div className="rounded border border-violet/40 bg-violet/5 p-2 text-sm">{predictionQ()}</div>
              <AnswerBox onSubmit={submitPrediction} placeholder="Your prediction…" />
            </div>
          )}
          <Transcript lines={lines} />
          {error && <div className="text-xs text-red">{error}</div>}
        </div>
        <WhatIfPanel c={session.case} expertName={expertName} last={whatIf} onCheck={(q) => runWhatIf(q, "you").catch((e) => setError((e as Error).message))} />
        {expertLang !== "en" && (
          <div className="text-xs text-mute">{expertName} taught these rules in {LANGUAGES[expertLang].name}; the tutor translates their quotes.</div>
        )}
      </aside>
      {block && <BlockModal block={block} c={session.case} expertName={expertName} kind={voice.kind} onExplain={submitExplanation} onClose={closeBlock} />}
    </div>
  );
}

function BlockModal({ block, c, expertName, kind, onExplain, onClose }: {
  block: Block; c: Case; expertName: string; kind: VoiceKind; onExplain: (t: string) => void; onClose: () => void;
}) {
  const v = block.violations[0];
  const sm = v.screen_moment;
  const s = sm?.snapshot;
  const snapCase: Case | null = s?.alternatives ? {
    ...c, title: "", briefing: "", alternatives: s.alternatives, flight: s.flight ?? c.flight,
    origin: s.origin ?? c.origin, destination: s.destination ?? c.destination, weather: {},
    passenger: { ...c.passenger, tier: "-", deadline_reason: "", ...(s.passenger as object) },
  } as Case : null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="card fade-in max-h-[92vh] w-full max-w-4xl overflow-y-auto border-red/50 p-5">
        <div className="flex items-start gap-3">
          <span className="chip border-red/50 text-red">BLOCKED BEFORE SAVE</span>
          <div className="ml-auto text-xs text-mute">Deterministic guardrail · confirmed by {expertName}</div>
        </div>
        <h2 className="mt-3 text-xl font-bold">{expertName} would stop here.</h2>
        <p className="mt-1 text-text">{v.why}</p>
        {block.violations.length > 1 && (
          <div className="mt-2 text-xs text-mute">Also breaks: {block.violations.slice(1).map((x) => x.title).join(", ")}</div>
        )}

        {block.stage === "explain" && (
          <div className="mt-4 space-y-2">
            <div className="label">Why do you think that's a problem?</div>
            {kind === "simulated" ? <AnswerBox onSubmit={onExplain} placeholder="Explain the risk…" /> :
              <div className="text-sm text-mute">Answer the tutor out loud.</div>}
          </div>
        )}

        {block.stage === "revealed" && (
          <div className="mt-4 grid gap-4 md:grid-cols-[1fr_1.2fr]">
            <div className="space-y-3">
              {block.feedback && <div className="text-sm">{block.feedback}</div>}
              <div className="rounded-lg border border-sky/40 bg-sky/5 p-3">
                <div className="label">{expertName}'s words{v.expert_span ? ` · ${v.expert_span}` : ""}</div>
                <div className="mt-1 italic">“{v.expert_quote}”</div>
              </div>
              <div className="rounded-lg border border-line p-3 text-sm">
                <div className="label">Guardrail</div>
                <div className="mt-1">{v.guardrail}</div>
              </div>
              {block.counterfactuals.length > 0 && <Counterfactuals items={block.counterfactuals} />}
              <button className="btn btn-primary w-full" onClick={onClose}>Choose another option</button>
            </div>
            <div>
              <div className="label mb-1">{expertName}'s screen at {sm?.ts_label ?? "--:--"} (replay)</div>
              {snapCase && sm ? (
                <CaseBoard c={snapCase} compact readOnly maskName highlight={sm.option_id}
                           view={{ ...emptyView(), selected: sm.snapshot.selected ?? null, rejected: sm.snapshot.rejected ?? [], escalated: sm.snapshot.escalated ?? [] }} />
              ) : <div className="text-sm text-mute">Learned during the debrief (no screen moment).</div>}
            </div>
          </div>
        )}
        {block.stage === "explain" && <button className="btn btn-ghost mt-3 text-xs" onClick={onClose}>Skip and choose another option</button>}
      </div>
    </div>
  );
}

function MasteryCard({ m, expertName }: { m: any; expertName: string }) {
  const color: Record<string, string> = { mastered: "text-green border-green/40", coached: "text-sky border-sky/40", practice: "text-amber border-amber/40", in_progress: "text-mute" };
  return (
    <div className="card fade-in p-5">
      <div className="label">Mastery report</div>
      <h2 className="text-lg font-bold">{m.summary}</h2>
      <div className="mt-1 text-sm text-mute">Rebooked on option {m.final_option} · {m.interventions} intervention(s) · rules taught by {expertName}</div>
      <div className="mt-3 space-y-2">
        {m.items.map((i: any) => (
          <div key={i.rule_id} className="flex items-center gap-3 rounded-lg border border-line p-2.5 text-sm">
            <span className={`chip ${color[i.status]}`}>{i.status.toUpperCase().replace("_", " ")}</span>
            <div>
              <div className="font-semibold">{i.title}</div>
              <div className="text-xs text-mute">{i.label}{i.predicted ? " · predicted it up front" : ""}</div>
            </div>
          </div>
        ))}
      </div>
      {m.practice_next.length > 0 && <div className="mt-3 text-sm"><b>Practise next:</b> {m.practice_next.join(", ")}</div>}
    </div>
  );
}

function WhatIfPanel({ c, expertName, last, onCheck }: {
  c: Case; expertName: string; last: WhatIf | null; onCheck: (q: WhatIfQuery) => void;
}) {
  const [optionId, setOptionId] = useState(c.alternatives[0]?.id ?? "");
  const [conn, setConn] = useState("");
  const [arrival, setArrival] = useState("");
  const [bag, setBag] = useState<"" | "yes" | "no">("");
  const [approved, setApproved] = useState(false);
  const opt = c.alternatives.find((a) => a.id === optionId);
  const check = () => onCheck({
    option_id: optionId, connection_min: num(conn), arrival: arrival || undefined,
    checked_bag: bag === "" ? undefined : bag === "yes", has_supervisor_approval: approved,
  });
  const r = last?.result;
  return (
    <div className="card space-y-3 p-4">
      <div>
        <div className="label">What if?</div>
        <div className="text-xs text-mute">Ask the tutor out loud, or try a change here. Runs {expertName}'s guardrails; nothing is booked.</div>
      </div>
      <div className="grid grid-cols-2 gap-2 text-sm">
        <label className="col-span-2">
          <span className="label">Option</span>
          <select className="mt-1 w-full rounded-lg border border-line bg-ink px-2 py-1.5" value={optionId} onChange={(e) => setOptionId(e.target.value)}>
            {c.alternatives.map((a) => <option key={a.id} value={a.id}>{a.id} · {a.label}</option>)}
          </select>
        </label>
        <label>
          <span className="label">Connection (min)</span>
          <input className="mt-1 w-full rounded-lg border border-line bg-ink px-2 py-1.5" inputMode="numeric" placeholder={String(opt?.connection_min ?? "")}
                 value={conn} onChange={(e) => setConn(e.target.value.replace(/[^0-9]/g, ""))} />
        </label>
        <label>
          <span className="label">Lands at</span>
          <input className="mt-1 w-full rounded-lg border border-line bg-ink px-2 py-1.5" placeholder={opt?.arrival ?? "HH:MM"}
                 value={arrival} onChange={(e) => setArrival(e.target.value)} />
        </label>
        <label>
          <span className="label">Checked bag</span>
          <select className="mt-1 w-full rounded-lg border border-line bg-ink px-2 py-1.5" value={bag} onChange={(e) => setBag(e.target.value as typeof bag)}>
            <option value="">As is ({c.passenger.checked_bag ? "yes" : "no"})</option>
            <option value="yes">Yes</option>
            <option value="no">No</option>
          </select>
        </label>
        <label className="flex items-end gap-1.5 pb-1.5 text-xs text-mute">
          <input type="checkbox" checked={approved} onChange={(e) => setApproved(e.target.checked)} /> Supervisor approved
        </label>
      </div>
      <button className="btn w-full" onClick={check} disabled={!optionId || (!!arrival && !/^\d{1,2}:\d{2}$/.test(arrival))}>Check against {expertName}'s rules</button>
      {r && (
        <div className={`fade-in rounded-lg border p-3 text-sm ${r.allowed ? "border-green/40" : "border-red/40"}`}>
          <div className="flex items-center gap-2">
            <span className={`chip ${r.allowed ? "border-green/40 text-green" : "border-red/40 text-red"}`}>{r.allowed ? "ALLOWED" : "BLOCKED"}</span>
            <span className="text-xs text-mute">
              Option {r.option_id}{Object.keys(r.changed).length ? ` · ${Object.entries(r.changed).map(([k, v]) => `${k.replace("_", " ")} ${v}`).join(", ")}` : " · as is"}
              {last?.source === "tutor" ? " · asked via tutor" : ""}
            </span>
          </div>
          {r.violations.map((v) => <div key={v.rule_id} className="mt-2"><b>{v.title}.</b> {v.why}</div>)}
          {r.allowed && <div className="mt-2">None of {expertName}'s confirmed rules would stop this.</div>}
          {!r.allowed && r.would_pass_if.length > 0 && <div className="mt-2"><Counterfactuals items={r.would_pass_if} /></div>}
          {r.draft_warnings.length > 0 && <div className="mt-2 text-xs text-amber">Draft (unconfirmed): {r.draft_warnings.map((v) => v.title).join(", ")}</div>}
        </div>
      )}
    </div>
  );
}

function Counterfactuals({ items }: { items: Counterfactual[] }) {
  return (
    <div className="rounded-lg border border-green/30 bg-green/5 p-3 text-sm">
      <div className="label">Smallest change that would pass · Z3</div>
      <ul className="mt-1 space-y-0.5">
        {items.map((cf, i) => <li key={i}>{i > 0 && <span className="text-mute">or </span>}{cf.text.replace(/^Allowed if /, "").replace(/\.$/, "")}</li>)}
      </ul>
    </div>
  );
}
