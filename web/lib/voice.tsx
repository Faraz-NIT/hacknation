"use client";
/**
 * One voice interface, two engines:
 *  - "elevenlabs": ElevenAgents over WebSocket with client tools (the real product)
 *  - "simulated":  browser speechSynthesis + typed/dictated answers, so the whole
 *                  Capture -> Map -> Teach loop can be rehearsed with no keys
 */
import { ConversationProvider, useConversation } from "@elevenlabs/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

export type VoiceKind = "elevenlabs" | "simulated";
export type ToolMap = Record<string, (params: any) => Promise<string> | string>;

export function VoiceProvider({ children }: { children: React.ReactNode }) {
  return <ConversationProvider>{children}</ConversationProvider>;
}

type StartOpts = {
  kind: VoiceKind;
  mode: "expert" | "trainee";
  prompt: string;
  firstMessage: string;
  dynamicVariables?: Record<string, string>;
  tools: ToolMap;
  /** ElevenAgents language override (needs "Language" enabled under the agent's Security → Overrides). */
  language?: string;
};

export function useVoiceAgent(handlers: {
  onUserText?: (text: string) => void;
  onAgentText?: (text: string) => void;
  onError?: (msg: string) => void;
}) {
  const h = useRef(handlers);
  h.current = handlers;
  const toolsRef = useRef<ToolMap>({});
  const [kind, setKind] = useState<VoiceKind>("simulated");
  const [connected, setConnected] = useState(false);
  const [simSpeaking, setSimSpeaking] = useState(false);
  const [micOpen, setMicOpenState] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);

  const conv = useConversation({
    onMessage: (m: { message: string; role?: string; source?: string }) => {
      const role = m.role ?? (m.source === "ai" ? "agent" : "user");
      if (!m.message || m.message.startsWith("[CONTROL")) return;
      if (role === "agent") h.current.onAgentText?.(m.message);
      else h.current.onUserText?.(m.message);
    },
    onConnect: () => setConnected(true),
    onDisconnect: () => setConnected(false),
    onError: (e: unknown) => {
      const msg = typeof e === "string" ? e : (e as Error)?.message ?? "ElevenLabs error";
      setLastError(msg);
      h.current.onError?.(msg);
    },
  } as any);

  const elSpeaking = conv.isSpeaking;
  const agentSpeaking = kind === "elevenlabs" ? elSpeaking : simSpeaking;

  const start = useCallback(async (opts: StartOpts) => {
    toolsRef.current = opts.tools;
    setKind(opts.kind);
    if (opts.kind === "simulated") {
      setConnected(true);
      return;
    }
    const cfg = await api.elevenlabs(opts.mode);
    if (!cfg.available) throw new Error(cfg.reason || "ElevenLabs not configured");
    // Client tools are proxied through a ref so pages can swap handlers without restarting.
    const clientTools: ToolMap = {};
    for (const name of Object.keys(opts.tools)) {
      clientTools[name] = async (params: any) => {
        try {
          const out = await toolsRef.current[name]?.(params ?? {});
          return typeof out === "string" ? out : JSON.stringify(out ?? "ok");
        } catch (err) {
          return `error: ${(err as Error).message}`;
        }
      };
    }
    const useOverrides = process.env.NEXT_PUBLIC_EL_USE_OVERRIDES !== "0";
    const session: any = {
      ...(cfg.signed_url ? { signedUrl: cfg.signed_url } : { agentId: cfg.agent_id }),
      connectionType: "websocket",
      clientTools,
      dynamicVariables: opts.dynamicVariables,
      ...(useOverrides ? { overrides: { agent: {
        prompt: { prompt: opts.prompt }, firstMessage: opts.firstMessage,
        ...(opts.language && opts.language !== "en" ? { language: opts.language } : {}),
      } } } : {}),
    };
    await navigator.mediaDevices.getUserMedia({ audio: true });
    conv.startSession(session);
  }, [conv]);

  const stop = useCallback(() => {
    if (kind === "elevenlabs") conv.endSession();
    if (typeof window !== "undefined") window.speechSynthesis?.cancel();
    setConnected(false);
  }, [conv, kind]);

  /** App-to-agent instruction. Simulated engine ignores it (pages drive it directly). */
  const control = useCallback((tag: string, payload: Record<string, unknown> = {}) => {
    if (kind !== "elevenlabs") return;
    const body = Object.entries(payload).map(([k, v]) => `${k}=${typeof v === "string" ? JSON.stringify(v) : JSON.stringify(v)}`).join(" ");
    conv.sendUserMessage(`[CONTROL:${tag}] ${body}`.trim());
  }, [conv, kind]);

  const context = useCallback((text: string) => {
    if (kind === "elevenlabs") conv.sendContextualUpdate(text);
  }, [conv, kind]);

  /** Mic gate: in capture mode the expert's mic only reaches the agent when an answer is expected. */
  const setMicOpen = useCallback((open: boolean) => {
    setMicOpenState(open);
    if (kind === "elevenlabs") conv.setMuted(!open);
  }, [conv, kind]);

  /** Simulated speech. Resolves when the utterance finishes. */
  const say = useCallback((text: string) => new Promise<void>((resolve) => {
    h.current.onAgentText?.(text);
    const synth = typeof window !== "undefined" ? window.speechSynthesis : undefined;
    setSimSpeaking(true);
    const done = () => { setSimSpeaking(false); resolve(); };
    if (!synth) { setTimeout(done, Math.min(6000, 60 * text.length)); return; }
    synth.cancel();
    const u = new SpeechSynthesisUtterance(text);
    const voices = synth.getVoices();
    u.voice = voices.find((v) => /en-(GB|US)/.test(v.lang) && /Google|Samantha|Daniel|Natural/i.test(v.name))
      ?? voices.find((v) => v.lang.startsWith("en")) ?? null;
    u.rate = 1.04;
    u.onend = done;
    u.onerror = done;
    synth.speak(u);
    setTimeout(() => { if (synth.speaking) return; done(); }, 400 + 90 * text.length);
  }), []);

  useEffect(() => () => { if (typeof window !== "undefined") window.speechSynthesis?.cancel(); }, []);

  return { kind, connected, agentSpeaking, micOpen, lastError, start, stop, control, context, setMicOpen, say,
           elStatus: conv.status };
}

/** Browser dictation for the simulated engine (Chrome / Edge). */
export function useDictation(onFinal: (text: string) => void, lang = "en-US") {
  const [listening, setListening] = useState(false);
  const recRef = useRef<any>(null);
  const supported = typeof window !== "undefined" && !!((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition);
  const start = useCallback(() => {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) return;
    const rec = new SR();
    rec.lang = lang;
    rec.interimResults = false;
    rec.continuous = false;
    rec.onresult = (e: any) => onFinal(Array.from(e.results).map((r: any) => r[0].transcript).join(" "));
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recRef.current = rec;
    rec.start();
    setListening(true);
  }, [onFinal, lang]);
  const stop = useCallback(() => recRef.current?.stop(), []);
  return { supported, listening, start, stop };
}
