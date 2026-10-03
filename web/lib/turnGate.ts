"use client";
/**
 * Turn gate: answers "when to ask".
 *
 * A queued question is released only when ALL of these hold:
 *   - the expert has not spoken for PAUSE_MS   (local voice-activity detector)
 *   - no typing / clicking / scrolling for PAUSE_MS
 *   - the agent is not speaking, nothing else is awaiting an answer, and we are on the record
 *
 * The VAD runs locally on a separate mic stream, so the agent itself can stay
 * muted while the expert narrates: it literally cannot interrupt them.
 */
import { useCallback, useEffect, useRef, useState } from "react";

export const PAUSE_MS = 1500;

export function useTurnGate(opts: { enabled: boolean; agentSpeaking: boolean; blocked: boolean }) {
  const lastVoice = useRef(0);
  const lastActivity = useRef(Date.now());
  const agentStoppedAt = useRef(0);
  const floor = useRef(0.01);
  const [vadOn, setVadOn] = useState(false);
  const [vadError, setVadError] = useState<string | null>(null);
  const [state, setState] = useState({ userSpeaking: false, speechIdle: 0, activityIdle: 0, level: 0, gateOpen: false });
  const levelRef = useRef(0);
  const streamRef = useRef<MediaStream | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const optsRef = useRef(opts);
  optsRef.current = opts;

  useEffect(() => {
    if (!opts.agentSpeaking) agentStoppedAt.current = Date.now();
  }, [opts.agentSpeaking]);

  const startVad = useCallback(async () => {
    if (ctxRef.current) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      streamRef.current = stream;
      const ctx = new AudioContext();
      ctxRef.current = ctx;
      const src = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 1024;
      src.connect(analyser);
      const buf = new Float32Array(analyser.fftSize);
      const loop = () => {
        if (!ctxRef.current) return;
        analyser.getFloatTimeDomainData(buf);
        let sum = 0;
        for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
        const rms = Math.sqrt(sum / buf.length);
        levelRef.current = rms;
        // Slow-adapting noise floor; speech must clearly exceed it.
        floor.current = rms < floor.current ? rms * 0.2 + floor.current * 0.8 : floor.current * 0.999 + rms * 0.001;
        const agentEcho = optsRef.current.agentSpeaking || Date.now() - agentStoppedAt.current < 500;
        if (!agentEcho && rms > Math.max(0.018, floor.current * 3)) lastVoice.current = Date.now();
        requestAnimationFrame(loop);
      };
      loop();
      setVadOn(true);
    } catch (e) {
      setVadError((e as Error).message || "microphone unavailable");
    }
  }, []);

  const stopVad = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    ctxRef.current?.close();
    ctxRef.current = null;
    setVadOn(false);
  }, []);

  useEffect(() => {
    const bump = () => { lastActivity.current = Date.now(); };
    const evs = ["keydown", "mousedown", "wheel", "pointermove", "touchstart"] as const;
    evs.forEach((e) => window.addEventListener(e, bump, { passive: true }));
    const id = window.setInterval(() => {
      const now = Date.now();
      const speechIdle = lastVoice.current ? now - lastVoice.current : 99_999;
      const activityIdle = now - lastActivity.current;
      const o = optsRef.current;
      const gateOpen = o.enabled && !o.blocked && !o.agentSpeaking && speechIdle >= PAUSE_MS && activityIdle >= PAUSE_MS;
      setState({ userSpeaking: speechIdle < 350, speechIdle, activityIdle, level: levelRef.current, gateOpen });
    }, 150);
    return () => { evs.forEach((e) => window.removeEventListener(e, bump)); clearInterval(id); };
  }, []);

  useEffect(() => stopVad, [stopVad]);

  return { ...state, vadOn, vadError, startVad, stopVad };
}
