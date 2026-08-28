"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef } from "react";

import { Badge } from "@/components/ui/badge";
import type { RunSummary, TranscriptStep } from "@/lib/api/transcript";
import { cn, formatMs, shortHash } from "@/lib/utils";

const KIND_LABEL: Record<string, string> = {
  graph_transition: "graph",
  agent_step: "agent",
  tool_call: "tool →",
  tool_result: "tool ←",
  gateway_decision: "sentinel",
  review: "review",
  error: "error",
  note: "note",
};

export function TranscriptPanel({
  run,
  reducedMotion,
}: {
  run: RunSummary;
  reducedMotion: boolean;
}) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth" });
  }, [run.transcript.steps.length, reducedMotion]);

  return (
    <div className="flex min-h-0 flex-col">
      {run.simulated_reasoning ? <OfflineBanner warning={run.warning} /> : null}

      <ol className="flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto p-3">
        <AnimatePresence initial={false}>
          {run.transcript.steps.map((step) => (
            <motion.li
              key={`${step.index}-${step.name}`}
              initial={reducedMotion ? false : { opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.18 }}
            >
              <StepRow step={step} />
            </motion.li>
          ))}
        </AnimatePresence>
        <div ref={endRef} />
      </ol>
    </div>
  );
}

function OfflineBanner({ warning }: { warning?: string }) {
  return (
    <div className="border-b border-signal-approval/30 bg-signal-approval/[0.08] px-4 py-3">
      <div className="flex items-center gap-2">
        <Badge tone="approval">Offline / scripted reasoning</Badge>
        <span className="font-mono text-[10px] uppercase tracking-wider text-signal-allow">
          Sentinel decisions are live
        </span>
      </div>
      <p className="mt-2 text-[11px] leading-relaxed text-chalk-muted">
        {warning ??
          "The agent's reasoning is a deterministic script, not a language model. Every scripted step is marked below. The gateway decisions, reason codes and audit hashes are real."}
      </p>
    </div>
  );
}

function StepRow({ step }: { step: TranscriptStep }) {
  const isGateway = step.kind === "gateway_decision";
  const isError = step.kind === "error";

  return (
    <div
      className={cn(
        "rounded-md border px-3 py-2",
        // The distinction the spec insists on: a scripted step never looks the
        // same as a live one. Violet left border + badge, everywhere, always.
        step.simulated
          ? "border-l-2 border-l-signal-simulated/70 border-hairline bg-signal-simulated/[0.04]"
          : "border-hairline-bright bg-ink-raised",
        isGateway && "border-signal-idle/40 bg-signal-idle/[0.05]",
        isError && "border-signal-block/50 bg-signal-block/[0.06]",
      )}
    >
      <div className="flex items-baseline gap-2">
        <span className="shrink-0 font-mono text-[9px] tabular-nums text-chalk-faint">
          {String(step.index).padStart(2, "0")}
        </span>
        <span className="shrink-0 font-mono text-[9px] uppercase tracking-wider text-chalk-faint">
          {KIND_LABEL[step.kind] ?? step.kind}
        </span>
        <span
          className={cn(
            "min-w-0 flex-1 truncate font-mono text-[11px]",
            isGateway ? "text-signal-idle" : "text-chalk",
          )}
        >
          {step.name}
        </span>
        {step.latency_ms !== null ? (
          <span className="shrink-0 font-mono text-[9px] tabular-nums text-chalk-faint">
            {formatMs(step.latency_ms)}
          </span>
        ) : null}
        {step.simulated ? (
          <Badge tone="simulated" className="shrink-0">
            scripted
          </Badge>
        ) : (
          <Badge tone="idle" className="shrink-0">
            live
          </Badge>
        )}
      </div>

      <p className="mt-1 pl-6 text-[11px] leading-relaxed text-chalk-muted">{step.summary}</p>

      <StepEvidence step={step} />
    </div>
  );
}

/**
 * Surfaces the two details that carry evidentiary weight, rather than dumping
 * the whole payload: the fetched page's hash (injection integrity) and the
 * gateway's reason codes.
 */
function StepEvidence({ step }: { step: TranscriptStep }) {
  const detail = step.detail ?? {};

  if (step.name === "fetch_merchant_page" && typeof detail.content_sha256 === "string") {
    const known = detail.is_known_injection_payload === true;
    return (
      <div className="mt-2 ml-6 rounded border border-hairline bg-ink/60 px-2.5 py-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="label-xs">sha-256</span>
          <code className="font-mono text-[10px] text-chalk">
            {shortHash(detail.content_sha256 as string, 24)}
          </code>
          {known ? (
            <Badge tone="block">known injection payload</Badge>
          ) : (
            <Badge tone="neutral">clean page</Badge>
          )}
        </div>
        <p className="mt-1.5 text-[10px] leading-relaxed text-chalk-faint">
          Hashed at the tool boundary — the bytes the agent actually received. Nothing
          upstream rewrote the content.
        </p>
      </div>
    );
  }

  if (step.kind === "gateway_decision") {
    const codes = Array.isArray(detail.reason_codes) ? (detail.reason_codes as string[]) : [];
    return codes.length ? (
      <div className="mt-2 ml-6 flex flex-wrap gap-1.5">
        {codes.map((code) => (
          <Badge key={code} tone={step.name === "ALLOW" ? "allow" : step.name === "BLOCK" ? "block" : "approval"}>
            {code}
          </Badge>
        ))}
      </div>
    ) : null;
  }

  return null;
}
