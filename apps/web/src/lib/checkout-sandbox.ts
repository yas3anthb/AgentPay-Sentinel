"use client";

import { useEffect, useRef, useState } from "react";

import type { PipelineState } from "@/lib/pipeline";
import type { RunSummary } from "@/lib/api/transcript";

export type CheckoutStep =
  | "idle"
  | "order_created"
  | "method_selected"
  | "authenticating"
  | "captured"
  | "declined"
  | "not_reached";

export const CHECKOUT_STEPS: { id: CheckoutStep; label: string }[] = [
  { id: "order_created", label: "Order created" },
  { id: "method_selected", label: "Payment method" },
  { id: "authenticating", label: "Authenticating" },
  { id: "captured", label: "Captured" },
];

const STEP_MS = 1100;

/**
 * Drives the simulated checkout strictly off the real authorization stage's
 * status — it never has an opinion of its own about whether a payment
 * succeeded. If the real pipeline never reaches authorization (a block), this
 * never starts. If it pauses for approval, this pauses too. The only thing
 * simulated is the visual vocabulary of an external checkout; the outcome
 * (captured vs declined) is read from the real `run.sentinel.state`.
 */
export function useCheckoutSandbox(pipeline: PipelineState, run: RunSummary | null) {
  const [step, setStep] = useState<CheckoutStep>("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastAuthStatus = useRef<string>("idle");

  // `run` arrives from a separate, later-resolving source than the pipeline's
  // own stage events: the simulator's HTTP response, versus the WebSocket
  // stage stream. If `run` were a dependency of the effect below, its arrival
  // — completely unrelated to which checkout step we are on — would re-run
  // the effect, whose cleanup clears the in-flight timer, freezing the
  // sequence wherever it happened to be (this really happened: a run would
  // stick on "Order created" forever). A ref sidesteps that: it is always
  // current when read, without ever forcing the effect to re-run.
  const runRef = useRef(run);
  runRef.current = run;

  useEffect(() => {
    const auth = pipeline.authorization;
    if (!auth || auth.status === lastAuthStatus.current) return;
    lastAuthStatus.current = auth.status;

    if (timer.current) clearTimeout(timer.current);

    if (auth.status === "idle") {
      setStep("idle");
    } else if (auth.status === "skipped") {
      // A block. The real authorization stage never ran, so neither does this.
      setStep("not_reached");
    } else if (auth.status === "paused") {
      // Awaiting human approval — same honesty rule as the real pipeline:
      // nothing proceeds, nothing is invented while we wait.
      setStep("order_created");
    } else if (auth.status === "started" || auth.status === "passed") {
      const sequence: CheckoutStep[] = ["order_created", "method_selected", "authenticating"];
      let i = 0;
      const advance = () => {
        if (i < sequence.length) {
          setStep(sequence[i]);
          i += 1;
          timer.current = setTimeout(advance, STEP_MS);
        } else {
          // Read the settled state at the moment the sequence actually ends,
          // not whatever (possibly still-null) value existed when it started.
          const settled = runRef.current?.sentinel?.state;
          setStep(settled === "FAILED" ? "declined" : "captured");
        }
      };
      advance();
    }

    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [pipeline.authorization?.status]);

  useEffect(() => {
    if (pipeline.authorization?.status === "idle") {
      setStep("idle");
      lastAuthStatus.current = "idle";
    }
  }, [pipeline.authorization?.status]);

  return step;
}
