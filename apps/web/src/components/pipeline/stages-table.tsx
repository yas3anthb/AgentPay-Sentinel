"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  STAGES,
  statusLabel,
  statusTone,
  type PipelineState,
} from "@/lib/pipeline";
import { cn, formatMs } from "@/lib/utils";

/**
 * The same pipeline data as a table: Stage / What it checked / Time / Result.
 * Plain language leads; the precise technical description is available on an
 * expander per row rather than shown by default.
 */
export function StagesTable({ state }: { state: PipelineState }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="border-b border-line">
            {["Stage", "What it checked", "Time", "Result"].map((h) => (
              <th key={h} className="label px-5 py-2.5 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {STAGES.map((stage) => {
            const s = state[stage.id];
            const isOpen = expanded === stage.id;
            const isIdle = s.status === "idle";
            return (
              <>
                <tr
                  key={stage.id}
                  className={cn(
                    "border-b border-line last:border-0",
                    !isIdle && "cursor-pointer hover:bg-surface-sunken",
                  )}
                  onClick={() => !isIdle && setExpanded(isOpen ? null : stage.id)}
                >
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-1.5">
                      <span className={cn("text-body font-medium", isIdle ? "text-ink-muted" : "text-ink")}>
                        {stage.label}
                      </span>
                      {!isIdle ? (
                        <ChevronDown
                          size={14}
                          className={cn(
                            "text-ink-muted transition-transform",
                            isOpen && "rotate-180",
                          )}
                        />
                      ) : null}
                    </div>
                  </td>
                  <td className="max-w-xs px-5 py-3 text-caption text-ink-secondary">
                    {stage.plain}
                  </td>
                  <td className="px-5 py-3 font-mono text-data text-ink-secondary">
                    {formatMs(s.latencyMs)}
                  </td>
                  <td className="px-5 py-3">
                    <Badge tone={isIdle ? "neutral" : statusTone(s.status)}>
                      {isIdle ? "Waiting" : statusLabel(s.status)}
                    </Badge>
                  </td>
                </tr>
                {isOpen ? (
                  <tr className="border-b border-line bg-surface-sunken last:border-0">
                    <td colSpan={4} className="px-5 py-3 text-caption text-ink-secondary">
                      <span className="label mr-2 text-ink-muted">Technical detail</span>
                      {stage.technical}
                    </td>
                  </tr>
                ) : null}
              </>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
