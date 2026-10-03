"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import CaseBoard, { emptyView } from "@/components/CaseBoard";
import { api, Case } from "@/lib/api";

const TYPE_ICON: Record<string, string> = {
  case_opened: "◎", alternative_rejected: "✕", alternative_selected: "✓", escalation_requested: "⇡", rebook_confirmed: "■",
};

export default function WorkMap({ sessionId }: { sessionId: string }) {
  const [wm, setWm] = useState<any>(null);
  const [caseData, setCaseData] = useState<Case | null>(null);
  const [active, setActive] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.workmap(sessionId), api.session(sessionId)])
      .then(([w, s]) => { setWm(w); setCaseData(s.case); const first = w.steps.findIndex((x: any) => x.judgment_call); setActive(first >= 0 ? first : 0); })
      .catch((e) => setError(e.message));
  }, [sessionId]);

  const exportMd = async () => {
    const md = await api.exportMd(sessionId);
    const url = URL.createObjectURL(new Blob([md], { type: "text/markdown" }));
    const a = document.createElement("a");
    a.href = url; a.download = `skymentor-guardrails-${sessionId}.md`; a.click();
    URL.revokeObjectURL(url);
  };

  if (error) return <div className="text-red">{error}</div>;
  if (!wm || !caseData) return <div className="text-mute">Loading Work Map…</div>;
  const step = wm.steps[active];
  const rulesById = Object.fromEntries(wm.rules.map((r: any) => [r.rule_id, r]));
  const snapCase: Case | null = step?.snapshot?.alternatives ? { ...caseData, alternatives: step.snapshot.alternatives } : caseData;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <div className="label">Module 2 · Work Map</div>
          <h1 className="text-2xl font-bold">How {wm.expert_name} handles a disrupted connection</h1>
          <div className="text-sm text-mute">{wm.case.title}</div>
        </div>
        <div className="ml-auto flex gap-2">
          <button className="btn" onClick={exportMd}>Export agent-ready guardrails (.md)</button>
          <Link className="btn btn-primary" href="/trainee">Teach a new hire →</Link>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 md:grid-cols-7">
        {[["Steps", wm.stats.steps], ["Judgment calls", wm.stats.judgment_calls], ["Guardrails", wm.stats.guardrails],
          ["Confirmed", wm.stats.confirmed_rules], ["Live questions", wm.stats.live_questions],
          ["Debrief Qs", wm.stats.debrief_questions], ["Corrections", wm.stats.corrections]].map(([k, v]) => (
          <div key={k as string} className="card p-3">
            <div className="label">{k}</div>
            <div className="num text-2xl font-semibold">{v as number}</div>
          </div>
        ))}
      </div>
      {!wm.teachback_confirmed && <div className="card border-amber/40 p-3 text-sm text-amber">Teach-back not confirmed yet: rules are drafts and won't block the new hire.</div>}

      {/* Timeline */}
      <div className="card overflow-x-auto p-4">
        <div className="flex min-w-max items-start">
          {wm.steps.map((s: any, i: number) => (
            <div key={s.event_id} className="flex items-start">
              <button onClick={() => setActive(i)}
                      className={`w-44 rounded-lg border p-3 text-left transition ${i === active ? "border-sky bg-sky/10" : "border-line hover:border-mute"}`}>
                <div className="flex items-center gap-2 text-xs">
                  <span className={`flex h-6 w-6 items-center justify-center rounded-full ${s.judgment_call ? "bg-amber/20 text-amber" : "bg-line text-mute"}`}>{TYPE_ICON[s.type]}</span>
                  <span className="num text-mute">{s.ts_label}</span>
                  <span className="ml-auto text-mute">#{s.step_no}</span>
                </div>
                <div className="mt-2 text-sm font-semibold leading-snug">{s.title}</div>
                <div className="mt-2 flex flex-wrap gap-1">
                  {s.judgment_call && <span className="chip border-amber/40 text-[9px] text-amber">JUDGMENT</span>}
                  {s.guardrails.length > 0 && <span className="chip border-red/40 text-[9px] text-red">{s.guardrails.length} GUARDRAIL</span>}
                </div>
              </button>
              {i < wm.steps.length - 1 && <div className="mt-8 h-px w-6 bg-line" />}
            </div>
          ))}
        </div>
      </div>

      {step && (
        <div className="grid gap-4 lg:grid-cols-[1fr_1.1fr]">
          <div className="card space-y-4 p-5">
            <div>
              <div className="label">Step {step.step_no} of {wm.steps.length}</div>
              <h2 className="text-lg font-bold">{step.title}</h2>
            </div>
            <Field k="Screen moment" v={`${step.ts_label} · ${step.option_id ? `option ${step.option_id}` : "case overview"}`} />
            <Field k="Decision" v={step.decision} />
            {step.question && <Field k="Apprentice asked (live, at a pause)" v={`“${step.question}”`} />}
            <div>
              <div className="label">Reason, in {wm.expert_name}'s words</div>
              {step.reasons.length === 0 && <div className="text-sm text-mute">Routine step: no judgment captured.</div>}
              {step.reasons.map((r: any) => (
                <div key={r.rule_id} className="mt-1.5 rounded-lg border border-sky/30 bg-sky/5 p-3">
                  <div className="italic">“{r.quote}”</div>
                  <div className="num mt-1 text-[11px] text-mute">{wm.expert_name} · said {r.span ?? r.ts_label}</div>
                  {r.notes?.map((n: string, k: number) => <div key={k} className="mt-1.5 border-t border-line pt-1.5 text-xs text-mute">{n}</div>)}
                </div>
              ))}
            </div>
            <div>
              <div className="label">Guardrails</div>
              {step.guardrails.length === 0 && <div className="text-sm text-mute">None on this step.</div>}
              {step.guardrails.map((g: any) => {
                const r = rulesById[g.rule_id];
                return (
                  <div key={g.rule_id} className="mt-1.5 rounded-lg border border-line p-3 text-sm">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold">{r?.title}</span>
                      <span className={`chip ml-auto ${g.confirmed ? "text-green border-green/40" : "text-amber border-amber/40"}`}>{g.confirmed ? "EXPERT-CONFIRMED" : "DRAFT"}</span>
                    </div>
                    <div className="mt-1">{g.text}</div>
                    {r?.exception && <div className="mt-1 text-xs text-mute">Exception: {r.exception}</div>}
                    <div className="mt-2 flex items-center gap-2 text-[11px] text-mute">
                      <span>confidence</span>
                      <div className="h-1.5 w-24 overflow-hidden rounded bg-line"><div className="h-full bg-sky" style={{ width: `${(r?.confidence ?? 0) * 100}%` }} /></div>
                      <span className="num">{Math.round((r?.confidence ?? 0) * 100)}%</span>
                      <span className="ml-auto num">{JSON.stringify(r?.condition)} → {r?.action}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
          <div className="space-y-2">
            <div className="label">Screen at {step.ts_label} (replay)</div>
            {snapCase && (
              <CaseBoard c={snapCase} compact readOnly highlight={step.option_id} maskName
                         view={{ ...emptyView(), selected: step.snapshot?.selected ?? null, rejected: step.snapshot?.rejected ?? [], escalated: step.snapshot?.escalated ?? [] }} />
            )}
            <div className="text-xs text-mute">Evidence: UI event + case snapshot + transcript span + model-structured rule + expert confirmation. Off-record moments are excluded ({wm.stats.off_record_events}).</div>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ k, v }: { k: string; v: string }) {
  return <div><div className="label">{k}</div><div className="mt-0.5">{v}</div></div>;
}
