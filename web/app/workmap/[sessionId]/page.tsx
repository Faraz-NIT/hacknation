"use client";
import { useParams } from "next/navigation";
import WorkMap from "@/components/WorkMap";

export default function WorkMapSession() {
  const { sessionId } = useParams<{ sessionId: string }>();
  return <WorkMap sessionId={sessionId} />;
}
