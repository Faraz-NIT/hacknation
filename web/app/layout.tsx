import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";
import WorkspaceNav from "@/components/WorkspaceNav";

export const metadata: Metadata = {
  title: "SkyMentor Live",
  description: "AI Apprentice for airline disruption operations",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <header className="ops-header sticky top-0 z-20">
          <div className="mx-auto flex max-w-[1440px] flex-wrap items-center gap-4 px-4 py-3">
            <Link href="/" className="flex items-center gap-2 font-bold tracking-tight">
              <span className="grid size-8 place-items-center rounded-full bg-sky text-board font-display text-lg">S</span>
              <span className="font-display text-lg uppercase">SkyMentor Live</span>
            </Link>
            <WorkspaceNav />
            <span className="ml-auto hidden font-mono text-[10px] uppercase text-board-foreground/60 md:block">AI Apprentice for disruption operations</span>
          </div>
        </header>
        <main className="mx-auto max-w-[1440px] px-4 py-6 sm:px-6">{children}</main>
      </body>
    </html>
  );
}
