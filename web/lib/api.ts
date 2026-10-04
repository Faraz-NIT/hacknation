import type { LangCode } from "./languages";

export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type Alternative = {
  id: string; label: string; hub: string; hub_city: string; carrier: string; alliance: string;
  departure: string; arrival: string; connection_min: number; price_eur: number; cabin: string;
  seats_left?: number | null; note?: string | null;
};
export type Case = {
  case_id: string; title: string; briefing: string; origin: string; destination: string;
  flight: { number: string; route: string; disrupted_leg: string; status: string; delay_min?: number | null; source: string };
  passenger: { name: string; pnr: string; checked_bag: boolean; arrival_deadline: string; deadline_reason: string;
               original_cabin: string; tier: string; email?: string; phone?: string };
  alternatives: Alternative[];
  weather: Record<string, { risk: string; wind_kph: number; gust_kph?: number; temp_c?: number; source: string }>;
  market: Record<string, unknown>[];
  provenance: Record<string, string>;
};
export type Session = { session_id: string; mode: "expert" | "trainee"; expert_session_id: string | null;
                        state: Record<string, any>; case: Case };
export type Question = { id: string; text: string; category: string; is_guardrail: boolean; event_id: string };
export type Score = { q: number; features: Record<string, number>; hypotheses: string[]; ask: boolean;
                      question: string | null; category: string | null; is_guardrail: boolean; reasons: string[] };
export type EventResp = { event_id: string; ts: number; ts_label: string; off_record: boolean; score: Score; question: Question | null };
export type Rule = {
  rule_id: string; decision_type: string; title: string; condition: Record<string, unknown>; action: string;
  reason: string; guardrail: string | null; threshold_min: number | null; escalation: string | null;
  exception: string | null; source_event_id: string | null; source_ts: number | null;
  source_transcript_span: string | null; quote: string | null; confidence: number;
  expert_confirmed: boolean; corrections: number; extracted_by: string; notes: string[];
};
export type Gap = { gap_id: string; question: string; mandatory: boolean; category: string; rule_id: string | null; field: string | null };
export type Debrief = { gaps: Gap[]; mandatory_open: number; answered: number; min_questions: number;
                        ready_for_teachback: boolean; teachback: string | null; teachback_confirmed: boolean;
                        complete: boolean; corrections: number };
export type ScreenMoment = { event_id: string; type: string; option_id: string | null; ts: number; ts_label: string; snapshot: Snapshot };
export type Intervention = { rule_id: string; decision_type: string; title: string; guardrail: string | null; why: string;
                             expert_quote: string; expert_span: string | null; screen_moment: ScreenMoment | null;
                             tutor_script: string; reveal_script: string; confirmed: boolean };
export type Snapshot = { case_id?: string; selected?: string | null; rejected?: string[]; escalated?: string[];
                         focus?: string | null; alternatives?: Alternative[]; passenger?: Record<string, unknown>;
                         flight?: Case["flight"]; origin?: string; destination?: string };

export type WhatIfQuery = { option_id: string; connection_min?: number; arrival?: string; cabin?: string;
                            checked_bag?: boolean; has_supervisor_approval?: boolean };
type WhatIfRule = { rule_id: string; title: string; guardrail: string | null; why: string; expert_quote: string | null };
export type WhatIfResult = { option_id: string; changed: Record<string, unknown>; allowed: boolean;
                             violations: WhatIfRule[]; draft_warnings: WhatIfRule[]; would_pass_if: Counterfactual[];
                             facts: Record<string, unknown>; rules_checked: number };
export type BenchGroup = { n: number; connection_correct: number; deadline_correct: number; approver_correct: number;
  field_accuracy: number; all_correct: number; z3_equivalent: number; unsafe_allow_rate: number; over_block_rate: number;
  live_questions: number; debrief_questions: number; corrections: number; teachback_confirmed: number; stuck: number;
  llm_calls: number; seconds: number };
export type BenchRun = { name: string; meta: { started: string; expert: string; extractor: string; seed: number;
  languages: string[]; n_sessions: number; llm_calls: number; minutes: number }; groups: Record<string, BenchGroup> };
/** Smallest change (found by Z3) that would make a blocked option pass. */
export type Counterfactual = { changes: Record<string, unknown>; levers: string[]; text: string };
export type Finding = { kind: "dead" | "inconsistent" | "subsumed" | "duplicate" | "unguarded"; rule_ids: string[]; text: string };
export type Verification = {
  rules_checked: number; findings: Finding[]; consistent: boolean; solver_ms: number; solver: string; scope: string;
  envelope: { shortest_connection_with_bag: number | null; connection_guarded: boolean; min_arrival_margin: number | null;
              deadline_guarded: boolean; upgrade_without_approval_allowed: boolean };
  options: { option_id: string; label: string; allowed: boolean; would_pass_if: Counterfactual[] }[];
};

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch {}
    throw new ApiError(r.status, String(detail));
  }
  const ct = r.headers.get("content-type") || "";
  return (ct.includes("json") ? r.json() : r.text()) as Promise<T>;
}
export class ApiError extends Error { constructor(public status: number, msg: string) { super(msg); } }

const post = <T,>(path: string, body: unknown) => req<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  health: () => req<{ ok: boolean; integrations: Record<string, boolean>; offline: boolean }>("/api/health"),
  reset: () => post("/api/reset", {}),
  warm: () => post<Record<string, Record<string, string>>>("/api/cache/warm", {}),
  createSession: (body: { mode: "expert" | "trainee"; expert_name?: string; live?: boolean; expert_session_id?: string; language?: LangCode }) =>
    post<Session>("/api/sessions", body),
  latest: (mode = "expert") => req<Session>(`/api/sessions/latest?mode=${mode}`),
  session: (id: string) => req<Session>(`/api/sessions/${id}`),
  context: (id: string) => req<{ text: string; mode: string; expert_name?: string; rules_text?: string; expert_language?: LangCode }>(`/api/sessions/${id}/context`),
  offRecord: (id: string, on: boolean) => post<{ off_record: boolean; ts: number }>(`/api/sessions/${id}/off_record`, { on }),
  event: (body: { session_id: string; type: string; option_id?: string | null; snapshot?: Snapshot; detail?: object; off_record?: boolean }) =>
    post<EventResp>("/api/events", body),
  asked: (qid: string) => post<{ asked_ts: number; ts_label: string }>(`/api/questions/${qid}/asked`, {}),
  logQuestion: (session_id: string, text: string, phase = "debrief", category = "debrief") =>
    post("/api/questions", { session_id, text, phase, category }),
  transcript: (session_id: string, role: "user" | "agent" | "system", text: string, off_record = false) =>
    post<{ ts: number; ts_label: string; text: string; off_record: boolean; redacted: boolean }>("/api/transcript", { session_id, role, text, off_record }),
  extract: (session_id: string, text: string) => post<{ rules: Rule[]; unresolved: boolean }>("/api/rules/extract", { session_id, text }),
  recordRule: (body: Record<string, unknown>) => post<Rule>("/api/rules/record", body),
  rules: (id: string) => req<Rule[]>(`/api/rules/${id}`),
  correct: (body: Record<string, unknown>) => post<{ rule: Rule; debrief: Debrief }>("/api/rules/correct", body),
  debrief: (id: string) => req<Debrief>(`/api/debrief/${id}`),
  answerGap: (body: Record<string, unknown>) => post<{ resolved: boolean; debrief: Debrief }>("/api/debrief/answer", body),
  confirm: (session_id: string) => post<Debrief>("/api/debrief/confirm", { session_id }),
  workmap: (id: string) => req<any>(`/api/workmap/${id}`),
  exportMd: (id: string) => req<string>(`/api/workmap/${id}/export`),
  evaluate: (body: { session_id: string; option_id: string; type?: "confirm" | "select"; has_supervisor_approval?: boolean }) =>
    post<{ allowed: boolean; violations: Intervention[]; warnings: Intervention[]; facts: Record<string, unknown>;
           counterfactuals: Counterfactual[] }>("/api/guardrails/evaluate", body),
  bench: () => req<BenchRun[]>("/api/bench"),
  verify: (id: string, scope: "session" | "team" = "session") => req<Verification>(`/api/verify/${id}?scope=${scope}`),
  whatIf: (body: WhatIfQuery & { session_id: string }) => post<WhatIfResult>("/api/guardrails/whatif", body),
  traineeAnswer: (body: { session_id: string; kind: "prediction" | "explanation"; text: string; rule_id?: string | null }) =>
    post<{ correct: boolean; matched_rules?: string[]; feedback?: string; rule_id?: string }>("/api/trainee/answer", body),
  mastery: (id: string) => req<any>(`/api/mastery/${id}`),
  elevenlabs: (mode: string) => req<{ available: boolean; signed_url?: string; agent_id?: string; reason?: string; warning?: string }>(`/api/elevenlabs/session?mode=${mode}`),
};
