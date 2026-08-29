"use client";

import {
  BookLock,
  CreditCard,
  FileCheck2,
  Gauge,
  Scale,
  ScanSearch,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";

import {
  STAGES,
  STAGE_INDEX,
  severedAt,
  statusLabel,
  type PipelineState,
  type StageId,
  type StageStatus,
} from "@/lib/pipeline";
import { cn, formatMs } from "@/lib/utils";

const ICONS: Record<StageId, LucideIcon> = {
  identity: ShieldCheck,
  canonical: FileCheck2,
  analyzer: ScanSearch,
  risk: Gauge,
  pdp: Scale,
  authorization: CreditCard,
  audit: BookLock,
};

const NODE: Record<StageStatus, string> = {
  idle: "border-line bg-surface text-ink-muted",
  started: "border-accent bg-accent-tint text-accent",
  passed: "border-allow-line bg-allow-tint text-allow",
  paused: "border-approval-line bg-approval-tint text-approval",
  blocked: "border-block bg-block-tint text-block",
  failed: "border-block bg-block-tint text-block",
  skipped: "border-line bg-surface-sunken text-inactive",
};

const RAIL: Record<"filled" | "blocked" | "pending", string> = {
  filled: "bg-allow",
  blocked: "bg-block",
  pending: "bg-line-strong",
};

/**
 * The enforcement pipeline as a delivery-tracker.
 *
 * The visual language is deliberately familiar — seven steps on a rail that
 * fills as it progresses — because the people who most need to read this are
 * not engineers. The behaviour underneath is unchanged: the rail terminates
 * exactly at the blocking stage, downstream stages render inactive, and the
 * audit node still completes because a blocked decision is still recorded.
 */
export function StepTracker({
  state,
  reducedMotion,
}: {
  state: PipelineState;
  reducedMotion: boolean;
}) {
  const breakAt = severedAt(state);

  return (
    <div className="px-5 py-7">
      <ol className="flex items-start" aria-label="Enforcement pipeline progress">
        {STAGES.map((stage, index) => {
          const status = state[stage.id].status;
          const latency = state[stage.id].latencyMs;
          const Icon = ICONS[stage.id];
          const isBreak = breakAt !== null && index === breakAt;
          const afterBreak = breakAt !== null && index > breakAt;
          const isLast = index === STAGES.length - 1;

          // The rail leaving this node.
          let rail: "filled" | "blocked" | "pending" = "pending";
          if (breakAt !== null && index >= breakAt) rail = index === breakAt ? "blocked" : "pending";
          else if (status === "passed" || status === "paused") rail = "filled";

          return (
            <li key={stage.id} className="flex min-w-0 flex-1 flex-col items-center">
              <div className="flex w-full items-center">
                {/* Left half-rail keeps every node optically centred. */}
                <span
                  className={cn(
                    "h-0.5 flex-1 rounded-full",
                    index === 0 ? "bg-transparent" : leftRail(state, index, breakAt),
                  )}
                />
                <span
                  title={`${stage.plain} — ${stage.technical}`}
                  className={cn(
                    "relative flex h-11 w-11 shrink-0 items-center justify-center rounded-panel border transition-colors",
                    NODE[status],
                    !reducedMotion && status === "started" && "animate-pulse-soft",
                  )}
                >
                  <Icon size={18} strokeWidth={1.75} aria-hidden />
                  {isBreak ? (
                    <span
                      aria-hidden
                      className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full border border-block-line bg-block text-[9px] font-semibold text-white"
                    >
                      !
                    </span>
                  ) : null}
                </span>
                <span
                  className={cn(
                    "h-0.5 flex-1 rounded-full",
                    isLast ? "bg-transparent" : RAIL[rail],
                    rail === "pending" && !isLast && "opacity-70",
                  )}
                />
              </div>

              <div className="mt-3 px-1 text-center">
                <div
                  className={cn(
                    "text-caption font-medium",
                    afterBreak || status === "idle" ? "text-ink-muted" : "text-ink",
                  )}
                >
                  {stage.label}
                </div>
                <div className="mt-0.5 text-label normal-case tracking-normal text-ink-muted">
                  {status === "idle" ? "Waiting" : statusLabel(status)}
                  {latency !== null ? ` · ${formatMs(latency)}` : ""}
                </div>
              </div>
            </li>
          );
        })}
      </ol>

      {breakAt !== null ? (
        <p className="mt-5 flex items-center justify-center gap-2 text-caption text-block">
          <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-block" />
          Stopped at {STAGES[breakAt].label}. The remaining steps never ran.
        </p>
      ) : null}
    </div>
  );
}

/** Colour of the rail arriving at `index`, mirroring the departing rail before it. */
function leftRail(state: PipelineState, index: number, breakAt: number | null): string {
  if (breakAt !== null && index > breakAt) return RAIL.pending;
  if (breakAt !== null && index === breakAt) return RAIL.filled;
  const previous = STAGES[index - 1];
  const status = state[previous.id].status;
  return status === "passed" || status === "paused" ? RAIL.filled : RAIL.pending;
}

export { STAGE_INDEX };
