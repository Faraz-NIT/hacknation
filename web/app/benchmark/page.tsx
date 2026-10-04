"use client";
import { useEffect, useState } from "react";
import { api, BenchGroup, BenchRun } from "@/lib/api";
import { LANGUAGES, LangCode } from "@/lib/languages";

const pct = (x: number) => `${Math.round(100 * x)}%`;

function groupLabel(key: string) {
  if (key === "all") return "All languages";
  const lang = key.split("/").pop() as LangCode;
  return LANGUAGES[lang]?.name ?? key;
}

export default function BenchmarkPage() {
  const [runs, setRuns] = useState<BenchRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.bench().then(setRuns).catch((e) => setError((e as Error).message)); }, []);

  return (
    <div className="space-y-5">
      <div className="max-w-3xl">
        <div className="label">Evaluation</div>
        <h1 className="text-2xl font-bold">Benchmark: simulated experts with hidden rules</h1>
        <p className="mt-1 text-mute">
          Each session gives a simulated expert a random hidden policy (connection floor 60–105 min, deadline margin 0–45 min,
          one of three approvers) and a language. The expert works the case, answers the apprentice and corrects the teach-back,
          all through the real backend. We then score what SkyMentor learned against the hidden policy, and use Z3 to prove
          whether the learned guardrails block exactly the same bookings.
        </p>
      </div>
      {error && <div className="text-red">{error}</div>}
      {!runs ? <div className="text-mute">Loading…</div> : runs.length === 0 ? (
        <div className="card p-5 text-sm">No runs yet. From <code>api/</code>: <code>python -m bench.run --help</code></div>
      ) : runs.map((run) => <RunCard key={run.name} run={run} />)}
    </div>
  );
}

function RunCard({ run }: { run: BenchRun }) {
  const m = run.meta;
  const rows = Object.entries(run.groups);
  return (
    <div className="card space-y-3 p-5">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-lg font-bold">{m.expert === "llm" ? "LLM expert" : "Template expert"} · {m.extractor === "llm" ? "Cerebras extraction" : "heuristic extraction"}</h2>
        <span className="num text-xs text-mute">{m.n_sessions} sessions · {m.llm_calls} LLM calls · {m.minutes} min · seed {m.seed} · {m.started}</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-sm">
          <thead>
            <tr className="label text-left">
              <th className="py-1.5 pr-3 font-normal">Language</th><th className="pr-3 font-normal">n</th>
              <th className="pr-3 font-normal">All 3 rules right</th><th className="pr-3 font-normal">Z3-equivalent</th>
              <th className="pr-3 font-normal">Unsafe allows</th><th className="pr-3 font-normal">Questions</th>
              <th className="pr-3 font-normal">Corrections</th><th className="pr-3 font-normal">LLM calls</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([key, g]) => <Row key={key} label={groupLabel(key)} g={g} total={key === "all"} />)}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Row({ label, g, total }: { label: string; g: BenchGroup; total: boolean }) {
  return (
    <tr className={`border-t border-line ${total ? "font-semibold" : ""}`}>
      <td className="py-2 pr-3">{label}</td>
      <td className="num pr-3">{g.n}</td>
      <td className="pr-3"><Bar v={g.all_correct} /></td>
      <td className="pr-3"><Bar v={g.z3_equivalent} /></td>
      <td className={`num pr-3 ${g.unsafe_allow_rate > 0 ? "text-red" : ""}`}>{(100 * g.unsafe_allow_rate).toFixed(1)}%</td>
      <td className="num pr-3">{g.live_questions.toFixed(1)} live + {g.debrief_questions.toFixed(1)} debrief</td>
      <td className="num pr-3">{g.corrections.toFixed(1)}</td>
      <td className="num pr-3">{g.llm_calls.toFixed(1)}</td>
    </tr>
  );
}

function Bar({ v }: { v: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 overflow-hidden rounded bg-line">
        <div className={`h-full ${v >= 0.9 ? "bg-green" : v >= 0.5 ? "bg-amber" : "bg-red"}`} style={{ width: pct(v) }} />
      </div>
      <span className="num">{pct(v)}</span>
    </div>
  );
}
