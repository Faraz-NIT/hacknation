"use client";
import type { Alternative, Case } from "@/lib/api";

export type BoardView = {
  selected: string | null;
  rejected: string[];
  escalated: string[];
  approved: string[];
  confirmed: string | null;
  focus: string | null;
};
export const emptyView = (): BoardView => ({ selected: null, rejected: [], escalated: [], approved: [], confirmed: null, focus: null });

type Action = "inspect" | "reject" | "select" | "escalate" | "confirm" | "unreject";

const CABIN: Record<string, string> = { economy: "Economy", premium_economy: "Premium Eco", business: "Business", first: "First" };

function Provenance({ label }: { label?: string }) {
  if (!label || label === "off") return null;
  const live = label === "live";
  const color = live ? "text-green border-green/40" : label.startsWith("cached") ? "text-amber border-amber/40" : "text-mute";
  return <span className={`chip ${color}`}>{live ? "● LIVE" : label.toUpperCase()}</span>;
}

export default function CaseBoard({
  c, view, onAction, readOnly = false, highlight = null, compact = false, maskName = false,
}: {
  c: Case; view: BoardView; onAction?: (a: Action, id: string) => void; readOnly?: boolean;
  highlight?: string | null; compact?: boolean; maskName?: boolean;
}) {
  const cheapest = [...c.alternatives].sort((a, b) => a.price_eur - b.price_eur)[0]?.id;
  const earliest = [...c.alternatives].sort((a, b) => a.arrival.localeCompare(b.arrival))[0]?.id;
  const p = c.passenger;
  const pad = compact ? "p-3" : "p-4";

  return (
    <div className={`space-y-3 ${compact ? "text-[13px]" : ""}`}>
      {/* Disruption banner */}
      <div className={`card disruption-hero ${pad} flex flex-wrap items-center gap-x-6 gap-y-2`}>
        <span className="route-watermark" aria-hidden="true">{c.destination}</span>
        <div>
          <div className="label">Disruption</div>
          <div className="route-title">{c.origin} <span className="text-sky">&rarr;</span> {c.destination}</div>
          <div className="font-semibold">
            <span className="num">{c.flight.number}</span> · {c.flight.disrupted_leg}{" "}
            <span className={`chip ml-1 ${c.flight.status === "cancelled" ? "text-red border-red/40" : "text-amber border-amber/40"}`}>
              {c.flight.status.toUpperCase()}{c.flight.delay_min ? ` +${c.flight.delay_min}m` : ""}
            </span>
          </div>
          {!compact && <div className="mt-1 text-sm text-mute">{c.briefing}</div>}
        </div>
        {!compact && (
          <div className="ml-auto flex flex-wrap items-center gap-2 text-xs text-mute">
            <span>Status</span><Provenance label={c.provenance.flight_status} />
            <span>Weather</span><Provenance label={c.provenance.weather} />
            <span>Fares</span><Provenance label={c.provenance.market} />
          </div>
        )}
      </div>

      {/* Passenger constraints */}
      <div className={`card ${pad} grid grid-cols-2 gap-3 md:grid-cols-5`}>
        <Field k="Passenger" v={maskName ? "[PASSENGER]" : `${p.name}`} sub={maskName ? "[PNR]" : p.pnr} mono />
        <Field k="Checked bag" v={p.checked_bag ? "Yes, 1 bag" : "Carry-on only"} />
        <Field k="Must land by" v={p.arrival_deadline} sub={compact ? undefined : p.deadline_reason} mono />
        <Field k="Ticketed cabin" v={CABIN[p.original_cabin] ?? p.original_cabin} />
        <Field k="Status tier" v={p.tier} />
      </div>

      {/* Alternatives */}
      <div>
        <div className="mb-3 flex flex-wrap items-center gap-3"><h2 className="font-display text-2xl uppercase">{c.alternatives.length} alternatives</h2><span className="label">Compare passenger constraints</span></div>
        <div className="alternatives-grid grid gap-3 sm:grid-cols-2">
        {c.alternatives.map((a) => (
          <Row key={a.id} a={a} c={c} view={view} cheapest={a.id === cheapest} earliest={a.id === earliest}
               readOnly={readOnly} highlight={highlight === a.id} compact={compact} onAction={onAction} />
        ))}
        </div>
      </div>

      {!readOnly && !compact && (
        <div className="flex items-center gap-3">
          <button className="btn btn-primary" disabled={!view.selected || !!view.confirmed}
                  onClick={() => view.selected && onAction?.("confirm", view.selected)}>
            Confirm rebooking {view.selected ? `(${c.alternatives.find((x) => x.id === view.selected)?.label})` : ""}
          </button>
          {view.confirmed && <span className="chip confirmation-chip text-green border-green/40" role="status">✓ Rebooked on option {view.confirmed}</span>}
        </div>
      )}
    </div>
  );
}

function Field({ k, v, sub, mono }: { k: string; v: string; sub?: string; mono?: boolean }) {
  return (
    <div>
      <div className="label">{k}</div>
      <div className={`font-semibold ${mono ? "num" : ""}`}>{v}</div>
      {sub && <div className="text-xs text-mute">{sub}</div>}
    </div>
  );
}

function Row({ a, c, view, cheapest, earliest, readOnly, highlight, compact, onAction }: {
  a: Alternative; c: Case; view: BoardView; cheapest: boolean; earliest: boolean; readOnly: boolean;
  highlight: boolean; compact: boolean; onAction?: (x: Action, id: string) => void;
}) {
  const rejected = view.rejected.includes(a.id);
  const selected = view.selected === a.id;
  const escalated = view.escalated.includes(a.id);
  const approved = view.approved.includes(a.id);
  const wx = c.weather?.[a.hub];
  const ring = highlight ? "outline outline-2 outline-amber -outline-offset-2 bg-amber/5"
    : selected ? "bg-sky/10" : view.focus === a.id ? "bg-panel-2" : "";
  return (
    <div className={`alternative-card space-y-3 ${selected ? "selected" : ""} ${view.focus === a.id ? "focused" : ""} ${ring} ${rejected ? "opacity-45" : ""}`} data-confirmed={view.confirmed === a.id}>
      <div className="flex items-center justify-between">
        <span className="option-letter font-display text-xl">{a.id}</span>
        {view.confirmed === a.id ? <span className="chip confirmation-chip text-green">✓ Rebooked</span> : selected && <span className="chip fade-in text-sky">✓ Selected</span>}
      </div>
      {!readOnly && <button type="button" className="label hover:text-sky" onClick={() => onAction?.("inspect", a.id)}>Inspect option {a.id} &rarr;</button>}
      <div>
        <div className="font-display text-2xl">
          <span className="num text-mute">{a.id}</span> {c.origin} → {a.hub !== "-" ? `${a.hub} → ` : ""}{c.destination}
        </div>
        {rejected && <span className="chip my-0.5 text-[9px] text-red border-red/40">RULED OUT</span>}
        <div className="text-xs text-mute">{a.carrier}{a.alliance ? ` · ${a.alliance}` : ""}{a.note ? ` · ${a.note}` : ""}</div>
      </div>
      <div className="grid grid-cols-2 gap-2 font-mono text-xs">
      <div className="num leading-tight">
        <div className="text-[11px] text-mute">dep {a.departure}</div>
        <div><b>arr {a.arrival}</b></div>
        {earliest && <div className="text-[10px] font-semibold text-sky">EARLIEST</div>}
      </div>
      <div className="num"><span className="label block">Connection</span>{a.hub === "-" ? "nonstop" : `${a.connection_min} min`}</div>
      <div className="num">€{a.price_eur}{cheapest && <div className="text-[10px] font-semibold text-green">CHEAPEST</div>}</div>
      <div><span className="label block">Cabin</span>{CABIN[a.cabin] ?? a.cabin}</div>
      <div className="text-xs">{wx ? <span className={wx.risk === "normal" ? "text-mute" : "text-amber"}>{wx.risk} · {wx.wind_kph} km/h</span> : <span className="text-mute">—</span>}</div>
      </div>
      <div className={`flex flex-wrap justify-end gap-1.5 ${readOnly && compact ? "hidden" : ""}`} onClick={(e) => e.stopPropagation()}>
        {readOnly ? (
          <div className="flex gap-1">
            {selected && <span className="chip text-sky border-sky/40">SELECTED</span>}
            {escalated && <span className="chip text-violet border-violet/40">ESCALATED</span>}
          </div>
        ) : (
          <>
            {rejected
              ? <button className="btn btn-ghost px-2 py-1 text-xs" onClick={() => onAction?.("unreject", a.id)}>Undo</button>
              : <button className="btn btn-danger px-2 py-1 text-xs" disabled={!!view.confirmed} onClick={() => onAction?.("reject", a.id)}>Rule out</button>}
            <button className="btn px-2 py-1 text-xs" disabled={rejected || escalated || !!view.confirmed}
                    onClick={() => onAction?.("escalate", a.id)}>
              {approved ? "Approved ✓" : escalated ? "Pending…" : "Escalate"}
            </button>
            <button className={`btn px-2 py-1 text-xs ${selected ? "btn-primary" : ""}`} disabled={rejected || !!view.confirmed}
                    onClick={() => onAction?.("select", a.id)}>
              {selected ? "Selected" : "Select"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
