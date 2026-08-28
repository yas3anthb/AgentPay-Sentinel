"use client";

import { STAGES } from "@/lib/pipeline";
import { usePrefersReducedMotion } from "@/lib/use-stage-events";

/**
 * The idle pipeline shown on the Overview page.
 *
 * Deliberately 2D and cheap: the landing page should not pay for a WebGL
 * context, and this doubles as the reduced-motion presentation. The real scene
 * lives in the Test Console, where it is driven by actual events.
 */
export function IdlePipelinePreview() {
  const reduced = usePrefersReducedMotion();

  return (
    <div className="relative h-[260px] w-full">
      <svg
        viewBox="0 0 520 260"
        className="h-full w-full"
        role="img"
        aria-label="The seven enforcement stages, idle"
      >
        <defs>
          <linearGradient id="beam" x1="0" x2="1">
            <stop offset="0%" stopColor="#4EC9C0" stopOpacity="0" />
            <stop offset="50%" stopColor="#4EC9C0" stopOpacity="0.9" />
            <stop offset="100%" stopColor="#4EC9C0" stopOpacity="0" />
          </linearGradient>
        </defs>

        <line x1="40" y1="130" x2="480" y2="130" stroke="#17212C" strokeWidth="1" />
        {!reduced ? (
          <line
            x1="40"
            y1="130"
            x2="480"
            y2="130"
            stroke="url(#beam)"
            strokeWidth="1.5"
            strokeDasharray="70 370"
          >
            <animate
              attributeName="stroke-dashoffset"
              from="440"
              to="-70"
              dur="4.5s"
              repeatCount="indefinite"
            />
          </line>
        ) : null}

        {STAGES.map((stage, i) => {
          const x = 40 + i * (440 / (STAGES.length - 1));
          return (
            <g key={stage.id}>
              <rect
                x={x - 9}
                y={121}
                width={18}
                height={18}
                rx={2}
                transform={`rotate(45 ${x} 130)`}
                fill="none"
                stroke="#243343"
                strokeWidth="1"
              />
              <circle cx={x} cy={130} r="2" fill="#4EC9C0" opacity="0.55" />
              <text
                x={x}
                y={166}
                textAnchor="middle"
                className="fill-chalk-faint font-mono"
                style={{ fontSize: 8, letterSpacing: "0.1em" }}
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
