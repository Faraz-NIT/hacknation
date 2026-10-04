"use client";
import { useEffect, useRef, useState } from "react";
import { PAUSE_MS } from "@/lib/turnGate";
import { useDictation } from "@/lib/voice";
import SkyBuddy from "@/components/SkyBuddy";

export type Line = { role: "user" | "agent" | "system"; text: string; ts_label?: string; off?: boolean; redacted?: boolean };

export function AgentHeader({ kind, connected, speaking, title, accent = "sky", paused = false }: {
  kind: string; connected: boolean; speaking: boolean; title: string; accent?: "sky" | "violet"; paused?: boolean;
}) {
  const mood = paused ? "paused" : !connected ? "offline" : speaking ? "speaking" : "listening";
  return (
    <div className="flex items-center gap-3">
      <SkyBuddy mood={mood} accent={accent} className="agent-buddy" />
      <div className="min-w-0 flex-1">
        <div className="font-display text-xl uppercase">{title}</div>
        <div className="text-xs text-mute">
          {kind === "elevenlabs" ? "ElevenAgents voice" : "Browser voice"} · {mood === "paused" ? "off the record" : mood}
        </div>
      </div>
      <div className="voice-wave" data-speaking={speaking && !paused && connected} aria-hidden="true">
        {[0, 1, 2, 3, 4].map((bar) => <span key={bar} style={{ animationDelay: `${bar * 110}ms` }} />)}
      </div>
    </div>
  );
}

export function GateMeter({ gate, pending, awaiting, offRecord, micOpen }: {
  gate: { userSpeaking: boolean; speechIdle: number; activityIdle: number; level: number; gateOpen: boolean; vadOn: boolean; vadError: string | null };
  pending: string | null; awaiting: boolean; offRecord: boolean; micOpen: boolean;
}) {
  const pause = Math.min(gate.speechIdle, gate.activityIdle);
  const pct = Math.min(100, (pause / PAUSE_MS) * 100);
  let status = "Waiting for a pause";
  if (offRecord) status = "Off the record · not listening";
  else if (awaiting) status = "Listening for the answer";
  else if (gate.userSpeaking) status = "Expert speaking · staying quiet";
  else if (gate.activityIdle < PAUSE_MS) status = "Expert working · staying quiet";
  else if (gate.gateOpen && pending) status = "Pause detected · asking";
  else if (gate.gateOpen) status = "Quiet · nothing worth asking";
  return (
    <div className="rounded-lg border border-line bg-ink/60 p-3 text-xs">
      <div className="mb-2 flex items-center justify-between">
        <span className="label">Turn gate</span>
        <span className={`chip ${micOpen ? "text-green border-green/40" : "text-mute"}`}>agent mic {micOpen ? "open" : "muted"}</span>
      </div>
      <div className="mb-1.5 flex items-center gap-2">
        <span className="w-14 text-mute">voice</span>
        <div className="h-1.5 flex-1 overflow-hidden rounded bg-line">
          <div className={`h-full ${gate.userSpeaking ? "bg-amber" : "bg-mute"}`} style={{ width: `${Math.min(100, gate.level * 900)}%` }} />
        </div>
        <span className="w-16 text-right text-mute">{gate.vadOn ? "VAD on" : gate.vadError ? "no mic" : "VAD off"}</span>
      </div>
      <div className="mb-2 flex items-center gap-2">
        <span className="w-14 text-mute">pause</span>
        <div className="h-1.5 flex-1 overflow-hidden rounded bg-line">
          <div className={`h-full ${pct >= 100 ? "bg-green" : "bg-sky"}`} style={{ width: `${pct}%` }} />
        </div>
        <span className="num w-16 text-right">{(Math.min(pause, 9999) / 1000).toFixed(1)}s</span>
      </div>
      <div className="font-semibold">{status}</div>
      {pending && !awaiting && (
        <div className="mt-2 rounded border border-amber/40 bg-amber/5 p-2 text-amber">
          <span className="label text-amber">Queued question</span>
          <div className="mt-0.5">{pending}</div>
        </div>
      )}
    </div>
  );
}

export function Transcript({ lines }: { lines: Line[] }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    end.current?.scrollIntoView({ behavior: reduced ? "instant" : "smooth", block: "nearest" });
  }, [lines.length]);
  return (
    <div className="max-h-[340px] min-h-[140px] space-y-2 overflow-y-auto pr-1 text-sm">
      {lines.length === 0 && <div className="text-mute">Conversation will appear here. Personal data is redacted before storage.</div>}
      {lines.map((l, i) => (
        <div key={i} className={`fade-in ${l.role === "agent" ? "" : l.role === "system" ? "text-xs text-mute" : "pl-6"}`}>
          <div className="flex items-baseline gap-2">
            <span className={`text-[11px] font-semibold ${l.role === "agent" ? "text-sky" : l.role === "user" ? "text-amber" : "text-mute"}`}>
              {l.role === "agent" ? "AGENT" : l.role === "user" ? "YOU" : "·"}
            </span>
            {l.ts_label && <span className="num text-[10px] text-mute">{l.ts_label}</span>}
            {l.redacted && <span className="chip text-[9px] text-green border-green/30">PII redacted</span>}
            {l.off && <span className="chip text-[9px] text-amber border-amber/30">off record</span>}
          </div>
          <div className={l.off ? "italic text-mute" : ""}>{l.text}</div>
        </div>
      ))}
      <div ref={end} />
    </div>
  );
}

export function AnswerBox({ onSubmit, placeholder = "Type or dictate your answer…", disabled = false, autoFocus = true, lang }: {
  onSubmit: (text: string) => void; placeholder?: string; disabled?: boolean; autoFocus?: boolean; lang?: string;
}) {
  const [text, setText] = useState("");
  const dict = useDictation((t) => setText((prev) => (prev ? prev + " " : "") + t), lang);
  const submit = () => { const t = text.trim(); if (!t) return; onSubmit(t); setText(""); };
  return (
    <div className="fade-in flex gap-2">
      <input className="flex-1 rounded-lg border border-line bg-ink px-3 py-2 text-sm outline-none focus:border-sky"
             value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} disabled={disabled}
             autoFocus={autoFocus} onKeyDown={(e) => e.key === "Enter" && submit()} />
      {dict.supported && (
        <button className={`btn px-3 ${dict.listening ? "border-amber text-amber" : ""}`} disabled={disabled}
                onClick={() => (dict.listening ? dict.stop() : dict.start())} title="Dictate">
          {dict.listening ? "■" : "🎙"}
        </button>
      )}
      <button className="btn btn-primary" onClick={submit} disabled={disabled || !text.trim()}>Send</button>
    </div>
  );
}
