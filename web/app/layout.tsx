import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "SkyMentor Live",
  description: "AI Apprentice for airline disruption operations",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <header className="border-b border-line">
          <div className="mx-auto flex max-w-[1400px] items-center gap-6 px-4 py-3">
            <Link href="/" className="flex items-center gap-2 font-bold tracking-tight">
              <span className="inline-block h-2.5 w-2.5 rounded-full bg-sky" />
              SkyMentor <span className="text-sky">Live</span>
            </Link>
            <nav className="flex gap-4 text-sm text-mute">
              <Link href="/expert" className="hover:text-text">1 · Capture</Link>
              <Link href="/workmap" className="hover:text-text">2 · Work Map</Link>
              <Link href="/trainee" className="hover:text-text">3 · Teach</Link>
            </nav>
            <span className="ml-auto text-xs text-mute">AI Apprentice for disruption operations</span>
          </div>
        </header>
        <main className="mx-auto max-w-[1400px] px-4 py-5">{children}</main>
      </body>
    </html>
  );
}
