"use client";

import { DecisionPill } from "@/components/ui/badge";
import {
  severedAt,
  STAGES,
  statusColor,
  statusLabel,
  type PipelineState,
} from "@/lib/pipeline";
import type { RunPhase } from "@/lib/store";
import { cn } from "@/lib/utils";

/**
 * A single-row summary of the real Sentinel run — deliberately *not* the full
 * enforcement pipeline the Test Console renders. Here it is context, not the
 * subject: enough to see that a real decision gated the checkout below, and at
 * which stage it stopped, without reproducing the Console's centrepiece.
 */
export function SentinelRibbon({
  pipeline,
  phase,
  decision,
}: {
  pipeline: PipelineState;
  phase: RunPhase;
  decision: string | null | undefined;
}) {
  const severed = severedAt(pipeline);

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-3 rounded-panel border border-line bg-surface px-4 py-3">
      <span className="label shrink-0">Sentinel gateway</span>

      <ol className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
        {STAGES.map((stage, i) => {
          const status = pipeline[stage.id].status;
          const dimmed = severed !== null && i > severed;
          return (
            <li key={stage.id} className="flex items-center gap-1">
              <span
                title={`${stage.label} — ${statusLabel(status)}`}
                className={cn(
                  "h-2 w-2 shrink-0 rounded-full",
                  dimmed && "opacity-30",
                )}
                style={{ backgroundColor: statusColor(status) }}
              />
              <span
                className={cn(
                  "hidden whitespace-nowrap text-label text-ink-muted sm:inline",
                  dimmed && "opacity-40",
                )}
              >
                {stage.short}
              </span>
              {i < STAGES.length - 1 ? (
                <span className="mx-0.5 h-px w-3 shrink-0 bg-line-strong" aria-hidden />
              ) : null}
            </li>
          );
        })}
      </ol>

      <div className="shrink-0">
        {phase === "running" ? (
          <span className="text-label text-ink-muted">Checking…</span>
        ) : decision ? (
          <DecisionPill decision={decision} />
        ) : (
          <span className="text-label text-ink-muted">Idle</span>
        )}
      </div>
    </div>
  );
}
