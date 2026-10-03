"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const MODULES = [
  { n: "1", href: "/expert", title: "Capture", sub: "Expert judgment",
    body: "The expert solves a live disruption. The apprentice stays quiet while they talk or work and asks short questions only at natural pauses." },
  { n: "2", href: "/workmap", title: "Map", sub: "Structured memory",
    body: "A spoken debrief closes the gaps and ends with a teach-back. The result is a clickable Work Map with reasons, guardrails and evidence." },
  { n: "3", href: "/trainee", title: "Teach", sub: "Transfer of judgment",
    body: "A new hire handles an unseen case. A deterministic guardrail stops a risky confirm and the tutor explains it in the expert's words." },
];

export default function Home() {
  const [health, setHealth] = useState<{ integrations: Record<string, boolean>; offline: boolean } | null>(null);
  const [down, setDown] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => { api.health().then(setHealth).catch(() => setDown(true)); }, []);

  return (
    <div className="space-y-8">
      <section className="disruption-hero rounded-3xl">
        <div className="label">Hack-Nation × ElevenLabs · The AI Apprentice</div>
        <h1 className="mt-2 max-w-3xl font-display text-4xl uppercase leading-tight sm:text-6xl">
          Real-time APIs provide the facts. The expert provides the judgment. <span className="text-sky">SkyMentor captures the why.</span>
        </h1>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        {MODULES.map((m) => (
          <Link key={m.n} href={m.href} className="card group p-6 transition hover:border-sky">
            <div className="flex items-baseline gap-3">
              <span className="num text-3xl font-semibold text-sky">{m.n}</span>
              <div>
                <div className="font-display text-3xl uppercase">{m.title}</div>
                <div className="label">{m.sub}</div>
              </div>
            </div>
            <p className="mt-3 text-sm text-mute">{m.body}</p>
            <div className="mt-4 text-sm font-semibold text-sky group-hover:underline">Open →</div>
          </Link>
        ))}
      </section>

      <section className="card p-5">
        <div className="flex flex-wrap items-center gap-3">
          <div className="label">System</div>
          {down && <span className="text-sm text-red">Backend offline. Start it with: cd api && uvicorn app.main:app --port 8000</span>}
          {health && Object.entries(health.integrations).map(([k, v]) => (
            <span key={k} className={`chip ${v ? "text-green border-green/40" : "text-mute"}`}>{v ? "●" : "○"} {k.replace(/_/g, " ")}</span>
          ))}
          <div className="ml-auto flex gap-2">
            <button className="btn" onClick={async () => { setMsg("Warming cache…"); try { const r = await api.warm(); setMsg("Cache warmed: " + JSON.stringify(r.case_A)); } catch (e) { setMsg((e as Error).message); } }}>Warm live-data cache</button>
            <button className="btn btn-danger" onClick={async () => { await api.reset(); setMsg("Demo reset: all sessions cleared."); }}>Reset demo</button>
          </div>
        </div>
        {msg && <div className="mt-2 text-xs text-mute">{msg}</div>}
      </section>
    </div>
  );
}
