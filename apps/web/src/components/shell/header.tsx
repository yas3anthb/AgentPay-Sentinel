import Link from "next/link";

import { Nav } from "./nav";

export function Header() {
  return (
    <header className="sticky top-0 z-40 border-b border-white/5 bg-chrome">
      <div className="mx-auto flex h-16 max-w-[1560px] items-center justify-between gap-8 px-6">
        <Link href="/" className="flex items-center gap-3">
          <Wordmark />
          <div className="leading-none">
            <div className="text-body font-semibold tracking-tight text-chrome-bright">
              AgentPay <span className="font-normal text-chrome-text">Sentinel</span>
            </div>
          </div>
        </Link>
        <Nav />
      </div>
    </header>
  );
}

/**
 * A shield silhouette, not a badge — "Sentinel" is the product's own name for
 * itself, and a rounded-square badge with a checkmark reads as a generic
 * verification icon rather than a guard mark. The two-tone fold (a lighter
 * left face, a darker right face) gives it dimension without needing a
 * gradient or a drop shadow, which would fight the flat surfaces used
 * everywhere else in the product.
 */
function Wordmark() {
  return (
    <svg width="26" height="28" viewBox="0 0 32 34" fill="none" aria-hidden="true">
      <defs>
        <clipPath id="shieldLeftHalf">
          <rect x="0" y="0" width="16" height="34" />
        </clipPath>
      </defs>
      <path
        d="M16 2 27 6.6v8.5c0 8-4.9 13.6-11 15.9-6.1-2.3-11-7.9-11-15.9V6.6L16 2Z"
        fill="#4338CA"
      />
      <g clipPath="url(#shieldLeftHalf)">
        <path
          d="M16 2 27 6.6v8.5c0 8-4.9 13.6-11 15.9-6.1-2.3-11-7.9-11-15.9V6.6L16 2Z"
          fill="#6366F1"
        />
      </g>
      <path
        d="M10.3 16.8 13.6 20.1 21.7 12"
        stroke="white"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
