export type BuddyMood = "ready" | "listening" | "speaking" | "paused" | "offline";

/** A small flight-desk companion, drawn in SVG so it stays crisp at every size. */
export default function SkyBuddy({ mood = "ready", className = "", accent = "sky" }: {
  mood?: BuddyMood; className?: string; accent?: "sky" | "violet";
}) {
  return (
    <div className={`sky-buddy ${className}`} data-mood={mood} data-accent={accent} aria-hidden="true">
      <svg viewBox="0 0 200 200" fill="none">
        <ellipse className="buddy-shadow" cx="100" cy="180" rx="48" ry="7" fill="currentColor" opacity=".12" />
        <g className="buddy-body">
          <path d="M56 126 26 144l32 8M144 126l30 18-32 8" fill="var(--buddy-color)" stroke="var(--board)" strokeWidth="4" strokeLinejoin="round" />
          <rect x="63" y="117" width="74" height="54" rx="22" fill="var(--buddy-color)" stroke="var(--board)" strokeWidth="4" />
          <path d="m91 140 9-6 9 6-9 15-9-15Z" fill="var(--board-foreground)" />
          <path d="M78 169v8m44-8v8" stroke="var(--board)" strokeWidth="9" strokeLinecap="round" />
          <path d="M100 31v13" stroke="var(--buddy-color)" strokeWidth="5" strokeLinecap="round" />
          <circle className="buddy-antenna" cx="100" cy="27" r="7" fill="var(--accent)" stroke="var(--board)" strokeWidth="3" />
          <rect x="44" y="45" width="112" height="86" rx="35" fill="var(--buddy-color)" stroke="var(--board)" strokeWidth="4" />
          <path d="M57 63c12-16 31-18 50-15" stroke="var(--board-foreground)" strokeWidth="5" strokeLinecap="round" opacity=".45" />
          <rect x="57" y="68" width="86" height="45" rx="20" fill="var(--board)" />
          <g className="buddy-eyes">
            <rect x="74" y="81" width="12" height="17" rx="6" fill="var(--board-foreground)" />
            <rect x="114" y="81" width="12" height="17" rx="6" fill="var(--board-foreground)" />
          </g>
          <path className="buddy-smile" d="M93 103q7 6 14 0" stroke="var(--accent)" strokeWidth="3" strokeLinecap="round" />
          <path d="M39 83v19m122-19v19" stroke="var(--board)" strokeWidth="13" strokeLinecap="round" />
          <path d="M163 100v15q0 7-10 7h-16" stroke="var(--board)" strokeWidth="4" strokeLinecap="round" />
          <rect x="124" y="117" width="16" height="9" rx="4.5" fill="var(--accent)" />
        </g>
      </svg>
    </div>
  );
}
