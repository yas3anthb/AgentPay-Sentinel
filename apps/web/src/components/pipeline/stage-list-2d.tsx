"use client";

import { motion } from "framer-motion";

import { Badge } from "@/components/ui/badge";
import {
  STAGES,
  STAGE_INDEX,
  severedAt,
  statusColor,
  type PipelineState,
  type StageStatus,
} from "@/lib/pipeline";
import { cn, formatMs } from "@/lib/utils";

const STATUS_LABEL: Record<StageStatus, string> = {
  idle: "waiting",
  started: "running",
  passed: "passed",
  blocked: "BLOCKED",
  paused: "PAUSED",
  failed: "failed",
  skipped: "never reached",
};

/**
 * The 2D pipeline. This is the fallback when WebGL is unavailable, and it is
 * the same information the 3D scene shows — not a reduced version of it.
 */
export function StageList2D({
  state,
  reducedMotion = false,
  className,
}: {
  state: PipelineState;
  reducedMotion?: boolean;
  className?: string;
}) {
  const breakAt = severedAt(state);

  return (
    <ol className={cn("flex flex-col gap-1.5", className)} aria-label="Enforcement pipeline">
      {STAGES.map((stage) => {
        const s = state[stage.id];
        const color = statusColor(s.status);
        const isBreak = breakAt !== null && STAGE_INDEX[stage.id] === breakAt;
        const afterBreak = breakAt !== null && STAGE_INDEX[stage.id] > breakAt;

        return (
          <li key={stage.id}>
            <div
              className={cn(
                "relative flex items-center gap-3 rounded-md border px-3 py-2.5 transition-colors",
                s.status === "idle"
                  ? "border-hairline bg-ink-raised/40"
                  : "border-hairline-bright bg-ink-raised",
                afterBreak && s.status === "skipped" && "opacity-45",
              )}
              style={
                s.status !== "idle" && s.status !== "skipped"
                  ? { borderColor: `${color}55` }
                  : undefined
              }
            >
              <span
                aria-hidden
                className="relative flex h-2.5 w-2.5 shrink-0 items-center justify-center"
              >
                <span
                  className="h-2 w-2 rotate-45 rounded-[2px]"
                  style={{ backgroundColor: color }}
                />
                {s.status === "started" && !reducedMotion ? (
                  <span
                    className="absolute inset-0 rotate-45 animate-pulse-ring rounded-[2px]"
                    style={{ backgroundColor: color }}
                  />
                ) : null}
              </span>

              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-2">
                  <span className="font-mono text-[11px] text-chalk">{stage.label}</span>
                  <span className="truncate text-[11px] text-chalk-faint">{stage.blurb}</span>
                </div>
              </div>

              <span className="shrink-0 font-mono text-[10px] tabular-nums text-chalk-faint">
                {formatMs(s.latencyMs)}
              </span>
              <span
                className="shrink-0 font-mono text-[10px] uppercase tracking-wider"
                style={{ color }}
              >
                {STATUS_LABEL[s.status]}
              </span>
            </div>

            {isBreak ? (
              <motion.div
                initial={reducedMotion ? false : { opacity: 0, scaleX: 0.6 }}
                animate={{ opacity: 1, scaleX: 1 }}
                className="my-1 flex items-center gap-2 pl-6"
              >
                <span className="h-px flex-1 bg-gradient-to-r from-signal-block/70 to-transparent" />
                <Badge tone="block">beam severed here</Badge>
                <span className="h-px flex-1 bg-gradient-to-l from-signal-block/70 to-transparent" />
              </motion.div>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
