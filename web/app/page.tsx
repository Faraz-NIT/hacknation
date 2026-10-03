"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import SkyBuddy from "@/components/SkyBuddy";

const BUDDY_NOTES = [
  "You bring the judgment. I’ll catch the why.",
  "I listen first. Good questions can wait for a pause.",
  "One expert’s instinct. A whole team’s next move.",
];

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
  const [buddyNote, setBuddyNote] = useState(0);
  useEffect(() => { api.health().then(setHealth).catch(() => setDown(true)); }, []);

  return (
    <div className="space-y-8">
      <section className="disruption-hero home-hero rounded-3xl">
        <div className="hero-grid" aria-hidden="true" />
        <div className="hero-copy">
          <div className="hero-eyebrow"><span className="signal-pulse" /> The AI Apprentice · SkyMentor Live</div>
          <h1>Great judgment.<br /><span className="text-sky">Ready for takeoff.</span></h1>
          <p className="hero-description">Turn the decisions only your best people know how to make into knowledge your whole team can use.</p>
          <div className="mt-7 flex flex-wrap items-center gap-4">
            <Link href="/expert" className="btn btn-primary hero-cta">Enter the expert workspace <span aria-hidden="true">↗</span></Link>
            <span className="font-mono text-[10px] uppercase text-board-foreground/55">Capture. Map. Pass it on.</span>
          </div>
          <div className="hero-footer"><span>Built for the moments that matter</span><span>Hack-Nation × ElevenLabs</span></div>
        </div>
        <div className="buddy-stage">
          <svg className="flight-orbit" viewBox="0 0 360 320" fill="none" aria-hidden="true">
            <ellipse cx="180" cy="160" rx="166" ry="111" transform="rotate(-22 180 160)" stroke="currentColor" strokeDasharray="5 9" />
            <circle cx="42" cy="98" r="5" fill="var(--accent)" />
            <circle cx="309" cy="234" r="4" fill="var(--primary)" />
            <path className="orbit-plane" d="m286 49 22-8-8 22-4-10-10-4Z" fill="var(--primary)" />
          </svg>
          <span className="buddy-tag">Your judgment copilot</span>
          <button type="button" className="buddy-greeting" aria-label="Say hello to Sky, your judgment copilot" onClick={() => setBuddyNote((note) => (note + 1) % BUDDY_NOTES.length)}>
            <SkyBuddy className="hero-buddy" />
          </button>
          <div className="buddy-note" aria-live="polite"><span className="buddy-name">SKY / APPRENTICE</span><p key={buddyNote} className="fade-in">{BUDDY_NOTES[buddyNote]}</p></div>
        </div>
      </section>

      <section>
        <div className="mb-4 flex items-center gap-3"><h2 className="text-2xl uppercase">Instinct becomes a system.</h2><span className="journey-rule" aria-hidden="true" /><span className="label hidden sm:inline">Three steps. One shared playbook.</span></div>
        <div className="journey-grid grid gap-4 md:grid-cols-3">
        {MODULES.map((m, index) => (
          <Link key={m.n} href={m.href} className="card journey-card group p-6" style={{ animationDelay: `${index * 90}ms` }}>
            <div className="mb-6 flex items-center justify-between"><span className="journey-step">0{m.n} / FLIGHT PLAN</span><span className="journey-icon" aria-hidden="true">
              <svg viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                {m.n === "1" ? <><rect x="12" y="5" width="8" height="15" rx="4" /><path d="M8 15a8 8 0 0 0 16 0M16 23v5m-4 0h8" /></> : m.n === "2" ? <><rect x="3" y="12" width="7" height="8" rx="2" /><rect x="22" y="3" width="7" height="8" rx="2" /><rect x="22" y="22" width="7" height="8" rx="2" /><path d="M10 16h6V7h6m-6 9v10h6" /></> : <><path d="m3 12 13-7 13 7-13 7-13-7Zm5 3v8q8 7 16 0v-8m5-3v11" /></>}
              </svg>
            </span></div>
            <div className="flex items-baseline gap-3">
              <div>
                <div className="font-display text-4xl uppercase">{m.title}</div>
                <div className="label">{m.sub}</div>
              </div>
            </div>
            <p className="mt-3 text-sm text-mute">{m.body}</p>
            <div className="journey-link">Open {m.title.toLowerCase()} <span aria-hidden="true">↗</span></div>
          </Link>
        ))}
        </div>
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
        {msg && <div className="fade-in mt-2 text-xs text-mute" role="status">{msg}</div>}
      </section>
    </div>
  );
}
