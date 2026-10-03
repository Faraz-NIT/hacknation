"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import WorkMap from "@/components/WorkMap";
import { api } from "@/lib/api";

export default function LatestWorkMap() {
  const [sid, setSid] = useState<string | null>(null);
  const [missing, setMissing] = useState(false);
  useEffect(() => { api.latest("expert").then((s) => setSid(s.session_id)).catch(() => setMissing(true)); }, []);
  if (missing) return <div className="card p-5">No expert session yet. <Link className="text-sky underline" href="/expert">Run Capture first.</Link></div>;
  if (!sid) return <div className="text-mute">Loading…</div>;
  return <WorkMap sessionId={sid} />;
}
