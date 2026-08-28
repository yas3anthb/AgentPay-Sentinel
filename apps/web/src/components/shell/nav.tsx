"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/", label: "Overview" },
  { href: "/test", label: "Test Console" },
  { href: "/agents", label: "My Agents" },
  { href: "/audit", label: "Audit & Policy" },
];

export function Nav() {
  const pathname = usePathname();
  return (
    <nav aria-label="Primary" className="flex items-center gap-1">
      {LINKS.map((link) => {
        const active = pathname === link.href;
        return (
          <Link
            key={link.href}
            href={link.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "rounded px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.12em] transition-colors",
              active
                ? "bg-signal-idle/10 text-signal-idle"
                : "text-chalk-faint hover:bg-hairline/50 hover:text-chalk-muted",
            )}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
