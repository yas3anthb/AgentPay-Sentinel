"use client";

import { STAGES } from "@/lib/pipeline";
import { usePrefersReducedMotion } from "@/lib/use-stage-events";

/**
 * The idle pipeline shown on the Overview page.
 *
 * Deliberately lightweight SVG, not WebGL — the landing page should not pay
 * for a 3D context just to preview the product. Rounded nodes on a light
 * ground, matching the Test Console's step tracker so the preview reads as
 * the same system rather than a different diagram.
 */
export function IdlePipelinePreview() {
  const reduced = usePrefersReducedMotion();

  return (
    <div className="relative flex h-[260px] w-full items-center bg-surface-sunken">
      <svg
        viewBox="0 0 520 200"
        className="h-full w-full"
        role="img"
        aria-label="The seven enforcement stages, idle"
      >
        <defs>
          <linearGradient id="beam" x1="0" x2="1">
            <stop offset="0%" stopColor="#4F46E5" stopOpacity="0" />
            <stop offset="50%" stopColor="#4F46E5" stopOpacity="0.85" />
            <stop offset="100%" stopColor="#4F46E5" stopOpacity="0" />
          </linearGradient>
        </defs>

        <line x1="46" y1="100" x2="474" y2="100" stroke="#E3E6EB" strokeWidth="2" />
        {!reduced ? (
          <line
            x1="46"
            y1="100"
            x2="474"
            y2="100"
            stroke="url(#beam)"
            strokeWidth="2"
            strokeDasharray="80 348"
          >
            <animate
              attributeName="stroke-dashoffset"
              from="428"
              to="-80"
              dur="5s"
              repeatCount="indefinite"
            />
          </line>
        ) : null}

        {STAGES.map((stage, i) => {
          const x = 46 + i * (428 / (STAGES.length - 1));
          return (
            <g key={stage.id}>
              <rect
                x={x - 15}
                y={85}
                width={30}
                height={30}
                rx={8}
                fill="#FFFFFF"
                stroke="#D2D7E0"
                strokeWidth="1.5"
              />
              <circle cx={x} cy={100} r="3.5" fill="#8A93A3" />
              {/* Short codes only — full stage names ("Payment authorization")
                  are wider than the space between adjacent nodes at any
                  container width and will overlap their neighbours if used
                  here. The full names are what the Test Console's step
                  tracker shows, in HTML flow that wraps instead of colliding;
                  this SVG preview is decorative, so it stays compact. */}
              <text
                x={x}
                y={136}
                textAnchor="middle"
                className="fill-ink-secondary font-mono"
                style={{ fontSize: 10, fontWeight: 600, letterSpacing: "0.05em" }}
              >
                {stage.short}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
