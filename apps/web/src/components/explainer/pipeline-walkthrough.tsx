"use client";

import {
  BookLock,
  Clock,
  CreditCard,
  FileCheck2,
  Gauge,
  Pause,
  Play,
  RotateCcw,
  Scale,
  ScanSearch,
  ShieldAlert,
  ShieldCheck,
  SkipBack,
  SkipForward,
  UserCheck,
} from "lucide-react";
import { useState } from "react";

import { Badge, DecisionPill } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { Decision } from "@/lib/api/gateway";
import type { ExplainerRun } from "@/lib/explainer-data";
import { stageStateAt, useWalkthrough, type MarkerState } from "@/lib/explainer-state";
import { STAGES, type StageId } from "@/lib/pipeline";
import { cn } from "@/lib/utils";

const ICONS: Record<StageId, typeof ShieldCheck> = {
  identity: ShieldCheck,
  canonical: FileCheck2,
  analyzer: ScanSearch,
  risk: Gauge,
  pdp: Scale,
  authorization: CreditCard,
  audit: BookLock,
};

const NODE_STYLE: Record<MarkerState, string> = {
  idle: "border-line bg-surface text-ink-muted",
  at: "border-accent bg-accent-tint text-accent",
  passed: "border-allow-line bg-allow-tint text-allow",
  "awaiting-approval": "border-approval-line bg-approval-tint text-approval",
  blocked: "border-block bg-block-tint text-block",
  "never-reached": "border-line bg-surface-sunken text-inactive",
};

export function PipelineWalkthrough({
  decision,
  onDecisionChange,
  run,
}: {
  decision: Decision;
  onDecisionChange: (d: Decision) => void;
  run: ExplainerRun;
}) {
  const walk = useWalkthrough(decision);
  const [focused, setFocused] = useState<StageId | null>(null);

  const states = stageStateAt(decision, walk.step, walk.isPaused ? false : true);
  const focusedStage = STAGES.find((s) => s.id === focused) ?? STAGES[walk.step];

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-2">
        {(["ALLOW", "REQUIRE_APPROVAL", "BLOCK"] as Decision[]).map((d) => (
          <button
            key={d}
            onClick={() => onDecisionChange(d)}
            className={cn(
              "rounded-control border px-3 py-1.5 text-caption font-medium transition-colors",
              d === decision
                ? "border-accent/40 bg-accent-tint text-accent"
                : "border-line bg-surface text-ink-secondary hover:border-line-strong",
            )}
          >
            {d === "ALLOW" ? "Allowed run" : d === "REQUIRE_APPROVAL" ? "Approval-required run" : "Blocked run"}
          </button>
        ))}
      </div>

      {/* The path with the moving marker. */}
      <div className="overflow-x-auto rounded-panel border border-line bg-surface p-6">
        <ol className="flex min-w-[720px] items-start">
          {STAGES.map((stage, i) => {
            const state = states[stage.id];
            const Icon = ICONS[stage.id];
            const isLast = i === STAGES.length - 1;

            return (
              <li key={stage.id} className="flex min-w-0 flex-1 flex-col items-center">
                <div className="flex w-full items-center">
                  <span
                    className={cn(
                      "h-0.5 flex-1 rounded-full",
                      i === 0
                        ? "bg-transparent"
                        : states[STAGES[i - 1].id] === "passed" || states[STAGES[i - 1].id] === "at"
                          ? "bg-allow"
                          : "bg-line-strong",
                    )}
                  />
                  <button
                    onClick={() => setFocused(stage.id)}
                    onMouseEnter={() => setFocused(stage.id)}
                    title={stage.technical}
                    className={cn(
                      "relative flex h-12 w-12 shrink-0 items-center justify-center rounded-panel border-2 transition-colors",
                      NODE_STYLE[state],
                    )}
                  >
                    <Icon size={19} strokeWidth={1.75} />
                    {state === "at" ? (
                      <span className="absolute -inset-1.5 rounded-panel border-2 border-accent/40 animate-pulse-soft" />
                    ) : null}
                    {state === "blocked" ? (
                      <span className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-block text-white">
                        <ShieldAlert size={11} />
                      </span>
                    ) : null}
                    {state === "awaiting-approval" ? (
                      <span className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-approval text-white">
                        <UserCheck size={11} />
                      </span>
                    ) : null}
                  </button>
                  <span
                    className={cn(
                      "h-0.5 flex-1 rounded-full",
                      isLast ? "bg-transparent" : state === "passed" ? "bg-allow" : "bg-line-strong",
                    )}
                  />
                </div>
                <div className="mt-2.5 text-center">
                  <div className={cn("text-caption font-medium", state === "never-reached" ? "text-ink-muted" : "text-ink")}>
                    {stage.label}
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      </div>

      {/* Detail panel: exact strings from the Test Console's stage table. */}
      {focusedStage ? (
        <div className="rounded-panel border border-line bg-surface p-5">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-section text-ink">{focusedStage.label}</h3>
            {states[focusedStage.id] === "awaiting-approval" ? (
              <Badge tone="approval">Awaiting human input</Badge>
            ) : states[focusedStage.id] === "blocked" ? (
              <Badge tone="block">Stopped here</Badge>
            ) : states[focusedStage.id] === "never-reached" ? (
              <Badge tone="inactive">Never reached</Badge>
            ) : null}
          </div>
          <p className="mt-1.5 text-body text-ink-secondary">{focusedStage.plain}</p>
          <p className="mt-2 border-t border-line pt-2.5 text-caption text-ink-muted">
            <span className="label mr-1.5 text-ink-muted">What it checked</span>
            {focusedStage.technical}
          </p>
        </div>
      ) : null}

      {walk.isPaused ? (
        <div className="rounded-panel border border-approval-line bg-approval-tint p-4">
          <div className="flex items-center gap-2">
            <UserCheck size={16} className="text-approval" />
            <span className="text-caption font-medium text-approval">
              Awaiting human input — the real pipeline stops here too, not polling
            </span>
          </div>
          <Button variant="approve" size="sm" className="mt-3" onClick={walk.grantApproval}>
            Simulate human approval
          </Button>
        </div>
      ) : null}

      {/* Manual step-through, since a researcher will want to stop and read. */}
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" onClick={walk.reset}>
          <RotateCcw size={14} /> Restart
        </Button>
        <Button variant="secondary" size="sm" onClick={walk.prev} disabled={walk.step === 0}>
          <SkipBack size={14} /> Prev
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={walk.next}
          disabled={walk.atEnd || walk.isPaused}
        >
          Next <SkipForward size={14} />
        </Button>
        <Button
          variant="primary"
          size="sm"
          onClick={walk.togglePlay}
          disabled={walk.atEnd || walk.isPaused}
        >
          {walk.playing ? <Pause size={14} /> : <Play size={14} />}
          {walk.playing ? "Pause" : "Autoplay"}
        </Button>
        <span className="ml-1 flex items-center gap-1.5 text-label text-ink-muted">
          <Clock size={12} /> ~2.2s per stage — illustrative pacing, not a timing measurement
        </span>
      </div>

      {/* Outcome, from real data where available. */}
      <div className="rounded-panel border border-line bg-surface-sunken p-4">
        <div className="flex flex-wrap items-center gap-2">
          <DecisionPill decision={run.decision} />
          {run.reasonCodes.map((code) => (
            <Badge key={code} tone="neutral" className="font-mono normal-case tracking-normal">
              {code}
            </Badge>
          ))}
          <span className="ml-auto font-mono text-data text-ink-muted">
            {run.weightedScore.toFixed(2)} / 100
          </span>
        </div>
        <p className="mt-2 text-caption text-ink-secondary">
          {run.source ? (
            <>
              From a real transaction ({run.merchant}, {run.amount} {run.currency}) — audit
              event <code className="font-mono">{run.source.eventId.slice(0, 16)}…</code> at{" "}
              {new Date(run.source.occurredAt).toLocaleString()}.
            </>
          ) : (
            <>
              No {decision === "ALLOW" ? "allowed" : decision === "BLOCK" ? "blocked" : "approval-required"}{" "}
              transaction has run yet — this is a representative example, not a live measurement.
              Run the matching scenario in the Test Console to replace it with real data.
            </>
          )}
        </p>
      </div>
    </div>
  );
}
