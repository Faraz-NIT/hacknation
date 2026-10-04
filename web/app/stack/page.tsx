import type { Metadata } from "next";
import StackDemo from "@/components/StackDemo";

export const metadata: Metadata = {
  title: "Inside SkyMentor | Animated Stack Demo",
  description: "Follow an expert decision through SkyMentor's interface, voice agent, learning engine, and deterministic guardrails.",
};

export default function StackPage() {
  return <StackDemo />;
}
