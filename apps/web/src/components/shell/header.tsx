import Link from "next/link";

import { Nav } from "./nav";

export function Header() {
  return (
    <header className="sticky top-0 z-40 border-b border-hairline bg-ink/85 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-[1600px] items-center justify-between gap-6 px-5">
        <Link href="/" className="group flex items-center gap-2.5">
          <ShieldMark />
          <div className="leading-none">
            <div className="font-mono text-[13px] tracking-[0.16em] text-chalk">
              AGENTPAY <span className="text-signal-idle">SENTINEL</span>
            </div>
            <div className="mt-1 font-mono text-[9px] uppercase tracking-[0.18em] text-chalk-faint">
              pre-payment enforcement gateway
            </div>
          </div>
        </Link>
        <Nav />
      </div>
    </header>
  );
}

function ShieldMark() {
  return (
    <svg width="22" height="24" viewBox="0 0 22 24" fill="none" aria-hidden="true">
      <path
        d="M11 1.5 20 5v7.2c0 5-3.7 9.2-9 10.3-5.3-1.1-9-5.3-9-10.3V5l9-3.5Z"
        stroke="#4EC9C0"
        strokeWidth="1.1"
        opacity="0.85"
      />
      {/* The severed beam, as a mark: the line stops rather than passing through. */}
      <path d="M4.5 12h5" stroke="#4EC9C0" strokeWidth="1.4" />
      <path d="M12.5 12h5" stroke="#F2637A" strokeWidth="1.4" opacity="0.75" />
      <circle cx="11" cy="12" r="1.6" stroke="#4EC9C0" strokeWidth="1.1" />
    </svg>
  );
}
