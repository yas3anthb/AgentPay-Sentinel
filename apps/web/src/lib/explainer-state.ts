"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { STAGES, STAGE_INDEX, type StageId } from "@/lib/pipeline";
import type { Decision } from "@/lib/api/gateway";

export type MarkerState = "idle" | "at" | "passed" | "awaiting-approval" | "blocked" | "never-reached";

/**
 * Where the marker sits and what every stage looks like at this point in the
 * walkthrough, for a given decision branch and a given step index.
 *
 * The branch logic mirrors what the real pipeline actually does — proven in
 * the Test Console, not invented here: PDP is index 4; ALLOW and a granted
 * REQUIRE_APPROVAL both continue to Authorization (5) and Audit (6); a BLOCK
 * stops dead at PDP and stages after it are permanently `never-reached`, the
 * same "skipped" semantics `severedAt()` already encodes for live runs.
 */
export function stageStateAt(
  decision: Decision,
  step: number,
  approvalGranted: boolean,
): Record<StageId, MarkerState> {
  const pdpIndex = STAGE_INDEX.pdp;
  const result = {} as Record<StageId, MarkerState>;

  for (const stage of STAGES) {
    const i = STAGE_INDEX[stage.id];

    if (i < step) {
      result[stage.id] = "passed";
      continue;
    }
    if (i > step) {
      const stoppedHere = decision === "BLOCK" && step === pdpIndex;
      const pausedHere = decision === "REQUIRE_APPROVAL" && step === pdpIndex && !approvalGranted;
      result[stage.id] = stoppedHere || pausedHere ? "never-reached" : "idle";
      continue;
    }

    // i === step: the marker is here right now.
    if (i === pdpIndex && decision === "BLOCK") {
      result[stage.id] = "blocked";
    } else if (i === pdpIndex && decision === "REQUIRE_APPROVAL" && !approvalGranted) {
      result[stage.id] = "awaiting-approval";
    } else {
      result[stage.id] = "at";
    }
  }
  return result;
}

/** The last step index this decision's marker can ever reach. */
export function finalStep(decision: Decision, approvalGranted: boolean): number {
  if (decision === "BLOCK") return STAGE_INDEX.pdp;
  if (decision === "REQUIRE_APPROVAL" && !approvalGranted) return STAGE_INDEX.pdp;
  return STAGES.length - 1;
}

const STEP_MS = 2200;

export function useWalkthrough(decision: Decision) {
  const [step, setStep] = useState(0);
  const [approvalGranted, setApprovalGranted] = useState(false);
  const [playing, setPlaying] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clamp = useCallback(
    (n: number) => Math.max(0, Math.min(finalStep(decision, approvalGranted), n)),
    [decision, approvalGranted],
  );

  const reset = useCallback(() => {
    setStep(0);
    setApprovalGranted(false);
    setPlaying(false);
  }, []);

  useEffect(reset, [decision, reset]);

  const next = useCallback(() => setStep((s) => clamp(s + 1)), [clamp]);
  const prev = useCallback(() => setStep((s) => clamp(s - 1)), [clamp]);
  const grantApproval = useCallback(() => setApprovalGranted(true), []);

  useEffect(() => {
    if (!playing) return;
    const last = finalStep(decision, approvalGranted);
    if (step >= last) {
      setPlaying(false);
      return;
    }
    timer.current = setTimeout(next, STEP_MS);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [playing, step, decision, approvalGranted, next]);

  const atEnd = step >= finalStep(decision, approvalGranted);
  const isPaused =
    decision === "REQUIRE_APPROVAL" && step === STAGE_INDEX.pdp && !approvalGranted;

  return {
    step,
    playing: playing && !isPaused,
    isPaused,
    atEnd,
    next,
    prev,
    reset,
    grantApproval,
    togglePlay: () => setPlaying((p) => !p),
    stopPlay: () => setPlaying(false),
  };
}
