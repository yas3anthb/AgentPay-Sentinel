"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLayoutEffect, useRef, useState } from "react";
import { gsap } from "gsap";
import { Menu, X } from "lucide-react";

import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/", label: "Overview" },
  { href: "/test", label: "Test Console" },
  { href: "/sandbox", label: "Sandbox" },
  { href: "/how-it-works", label: "How It Works" },
  { href: "/agents", label: "My Agents" },
  { href: "/audit", label: "Audit & Policy" },
  { href: "/telegram", label: "Telegram" },
];

/**
 * Primary navigation.
 *
 * Desktop: five flat, always-visible links with the existing underline
 * active-state treatment — unchanged in spirit from before this pass.
 *
 * Mobile (<768px): a real port of react-bits' CardNav — the same GSAP height
 * timeline and staggered card reveal, fetched and read from its source before
 * porting. Its vendor default hides ALL links behind that same expand-on-tap
 * gesture on every viewport, including desktop; adopted as-is, that would mean
 * an extra tap plus an animation delay before reaching Test Console or Audit
 * on every visit, on a product used repeatedly by the same technical
 * audience. That is the "flashier default that clashes with the calm
 * enterprise tone" this prompt asked to tune down, so the expand mechanic is
 * kept where it is a genuine, standard pattern (collapsing nav on narrow
 * viewports) and not used to gate primary desktop navigation.
 */
export function Nav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const cardsRef = useRef<(HTMLAnchorElement | null)[]>([]);
  const timelineRef = useRef<gsap.core.Timeline | null>(null);

  useLayoutEffect(() => {
    const panel = panelRef.current;
    if (!panel) return;

    gsap.set(panel, { height: 0, overflow: "hidden" });
    gsap.set(cardsRef.current, { y: 12, opacity: 0 });

    const tl = gsap.timeline({ paused: true });
    tl.to(panel, { height: "auto", duration: 0.32, ease: "power2.out" });
    tl.to(
      cardsRef.current,
      { y: 0, opacity: 1, duration: 0.28, ease: "power2.out", stagger: 0.05 },
      "-=0.12",
    );
    timelineRef.current = tl;

    return () => {
      tl.kill();
      timelineRef.current = null;
    };
  }, []);

  const toggle = () => {
    const tl = timelineRef.current;
    if (!tl) return;
    if (open) {
      tl.reverse();
    } else {
      tl.play(0);
    }
    setOpen((v) => !v);
  };

  return (
    <>
      {/* Desktop: flat, always visible. No tap required to navigate. */}
      <nav
        aria-label="Primary"
        className="hidden h-11 items-center gap-1 rounded-full border border-white/10 bg-white/[0.04] px-1.5 md:flex"
      >
        {LINKS.map((link) => (
          <NavLink key={link.href} href={link.href} label={link.label} active={pathname === link.href} />
        ))}
      </nav>

      {/* Mobile: the ported CardNav mechanic. */}
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-label={open ? "Close menu" : "Open menu"}
        className="flex h-9 w-9 items-center justify-center rounded-control text-chrome-text hover:text-chrome-bright md:hidden"
      >
        {open ? <X size={18} /> : <Menu size={18} />}
      </button>

      <div
        ref={panelRef}
        className="absolute inset-x-0 top-full border-t border-white/10 bg-chrome md:hidden"
      >
        <div className="flex flex-col gap-2 p-3">
          {LINKS.map((link, i) => {
            const active = pathname === link.href;
            return (
              <Link
                key={link.href}
                ref={(el) => {
                  cardsRef.current[i] = el;
                }}
                href={link.href}
                onClick={() => {
                  timelineRef.current?.reverse();
                  setOpen(false);
                }}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "rounded-control border px-3.5 py-3 text-body font-medium transition-colors",
                  active
                    ? "border-accent-onDark/40 bg-white/5 text-chrome-bright"
                    : "border-white/10 text-chrome-text hover:bg-white/5 hover:text-chrome-bright",
                )}
              >
                {link.label}
              </Link>
            );
          })}
        </div>
      </div>
    </>
  );
}

function NavLink({ href, label, active }: { href: string; label: string; active: boolean }) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex h-8 items-center rounded-full px-3.5 text-caption font-medium transition-colors",
        active
          ? "bg-accent-onDark text-white shadow-[0_1px_0_0_rgb(255_255_255/0.08)_inset]"
          : "text-chrome-text hover:bg-white/[0.06] hover:text-chrome-bright",
      )}
    >
      {label}
    </Link>
  );
}
