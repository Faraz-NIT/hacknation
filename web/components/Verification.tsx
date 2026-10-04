"use client";
import { useEffect, useState } from "react";
import { api, Verification } from "@/lib/api";

const KIND: Record<string, { label: string; cls: string }> = {
  inconsistent: { label: "INCONSISTENT", cls: "border-red/40 text-red" },
  dead: { label: "NEVER FIRES", cls: "border-red/40 text-red" },
  unguarded: { label: "UNGUARDED", cls: "border-amber/40 text-amber" },
  subsumed: { label: "REDUNDANT", cls: "border-line text-mute" },
  duplicate: { label: "DUPLICATE", cls: "border-line text-mute" },
};

/** Z3 analysis of the learned guardrails: consistency, safe envelope, per-option counterfactuals. */
export default function VerificationPanel({ sessionId, expertName }: { sessionId: string; expertName: string }) {
  const [scope, setScope] = useState<"session" | "team">("session");
  const [v, setV] = useState<Verification | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setV(null);
    api.verify(sessionId, scope).then(setV).catch((e) => setError((e as Error).message));
  }, [sessionId, scope]);

  if (error) return <div className="card p-4 text-sm text-red">Verification unavailable: {error}</div>;
  const env = v?.envelope;
  return (
    <div className="card space-y-4 p-5">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <div className="label">Formal verification</div>
          <h2 className="text-lg font-bold">What the guardrails provably enforce</h2>
        </div>
        {v && (
          <span className={`chip ${v.consistent ? "border-green/40 text-green" : "border-red/40 text-red"}`}>
            {v.consistent ? "CONSISTENT" : "ISSUES FOUND"}
          </span>
        )}
        <div className="ml-auto flex items-center gap-2">
          {(["session", "team"] as const).map((s) => (
            <button key={s} className={`btn text-xs ${scope === s ? "btn-primary" : ""}`} onClick={() => setScope(s)}>
              {s === "session" ? `${expertName}'s rules` : "All experts"}
            </button>
          ))}
        </div>
      </div>

      {!v ? <div className="text-sm text-mute">Running solver…</div> : (
        <>
          <div className="grid gap-2 sm:grid-cols-3">
            <Tile k="Shortest connection allowed with a bag"
                  v={env!.connection_guarded ? `${env!.shortest_connection_with_bag} min` : "unguarded"} bad={!env!.connection_guarded} />
            <Tile k="Tightest arrival allowed"
                  v={env!.deadline_guarded ? marginText(env!.min_arrival_margin!) : "unguarded"} bad={!env!.deadline_guarded} />
            <Tile k="Upgrade without approval" v={env!.upgrade_without_approval_allowed ? "possible" : "always blocked"}
                  bad={env!.upgrade_without_approval_allowed} />
          </div>

          <div>
            <div className="label">Findings</div>
            {v.findings.length === 0 && <div className="mt-1 text-sm text-mute">No conflicts, dead rules, redundancies or gaps.</div>}
            {v.findings.map((f, i) => (
              <div key={i} className="mt-1.5 flex items-start gap-2 text-sm">
                <span className={`chip shrink-0 text-[9px] ${KIND[f.kind].cls}`}>{KIND[f.kind].label}</span>
                <span>{f.text}</span>
              </div>
            ))}
          </div>

          <div>
            <div className="label">Options on this case</div>
            <div className="mt-1 space-y-1.5">
              {v.options.map((o) => (
                <div key={o.option_id} className="flex flex-wrap items-baseline gap-2 rounded-lg border border-line p-2.5 text-sm">
                  <span className={`chip text-[9px] ${o.allowed ? "border-green/40 text-green" : "border-red/40 text-red"}`}>{o.allowed ? "ALLOWED" : "BLOCKED"}</span>
                  <span className="font-semibold">{o.option_id} · {o.label}</span>
                  {!o.allowed && o.would_pass_if.length > 0 && (
                    <span className="text-xs text-mute">{o.would_pass_if.map((cf) => cf.text.replace(/^Allowed if /, "").replace(/\.$/, "")).join("; or ")}</span>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div className="num text-[11px] text-mute">
            {v.rules_checked} rule(s) encoded as SMT constraints · {v.solver} · {v.solver_ms} ms · every result is a proof or a concrete counterexample, not a sample
          </div>
        </>
      )}
    </div>
  );
}

function marginText(m: number) {
  return m >= 0 ? `${m} min before deadline` : `${-m} min after deadline`;
}

function Tile({ k, v, bad }: { k: string; v: string; bad: boolean }) {
  return (
    <div className={`rounded-lg border p-3 ${bad ? "border-amber/40" : "border-line"}`}>
      <div className="label">{k}</div>
      <div className={`num mt-1 text-lg font-semibold ${bad ? "text-amber" : ""}`}>{v}</div>
    </div>
  );
}
