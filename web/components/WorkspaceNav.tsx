"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const destinations = [
  { href: "/expert", number: "01", label: "Capture" },
  { href: "/workmap", number: "02", label: "Work Map" },
  { href: "/trainee", number: "03", label: "Teach" },
  { href: "/stack", number: "↗", label: "The stack" },
];

export default function WorkspaceNav() {
  const pathname = usePathname();
  return <nav className="workspace-nav" aria-label="Workspace">
    {destinations.map(({ href, number, label }) => {
      const active = pathname === href || pathname.startsWith(href + "/");
      return <Link key={href} href={href} aria-current={active ? "page" : undefined}>
        <span className="nav-number">{number}</span>{label}<span className="nav-indicator" />
      </Link>;
    })}
  </nav>;
}
