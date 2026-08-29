"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { fromRaw, fromRun } from "@/components/console/decision-card";
import { isSimulatorError } from "@/lib/api/transcript";
import { reducePipeline } from "@/lib/pipeline";
import { approveRun, runRawIntent, runSimulation, type RawIntentForm } from "@/lib/run-scenario";
import { SCENARIOS, useConsole } from "@/lib/store";
import { useStageEvents } from "@/lib/use-stage-events";

export const DEFAULT_RAW: RawIntentForm = {
  merchantId: "merch_beanery",
  amount: "21.25",
  currency: "USD",
  sku: "BEAN-ETH-1KG",
  itemName: "Ethiopian whole bean 1kg",
  quantity: 2,
  purpose: "Monthly coffee restock for the office kitchen",
  merchantContent:
    "Single-origin Ethiopian coffee, 1kg whole bean, medium roast. Ships in 2 business days.",
  sourceType: "official_api",
};

export const DEFAULT_INSTRUCTION =
  "Restock the office kitchen with coffee, keep it under $100.";

/**
 * The scenario-running machinery shared by the Test Console and the Sandbox.
 *
 * Both surfaces drive the *same* Sentinel gateway with the *same* inputs — the
 * only difference is what they render around the result. Keeping the run logic
 * here means the two can never quietly drift apart: a fix to how a scenario is
 * dispatched, or how the live pipeline is subscribed, lands in both at once.
 */
export function useScenarioRunner() {
  const store = useConsole();
  const {
    scenario,
    phase,
    requestId,
    run,
    rawDecision,
    beginRun,
    setEvents,
    finishRun,
    finishRaw,
    failRun,
  } = store;

  const [rawForm, setRawForm] = useState<RawIntentForm>(DEFAULT_RAW);
  const [instruction, setInstruction] = useState(DEFAULT_INSTRUCTION);

  // The raw path carries its own X-Request-Id, so it can be watched precisely.
  // Agent runs go through the simulator, which does not forward that header,
  // so those watch the firehose instead.
  const { events, socketState, reset: resetEvents } = useStageEvents(
    scenario === "raw" ? requestId : null,
    true,
  );

  useEffect(() => setEvents(events), [events, setEvents]);
  const pipeline = useMemo(() => reducePipeline(events), [events]);

  const busy = phase === "running";

  const start = useCallback(async () => {
    resetEvents();
    const def = SCENARIOS.find((s) => s.id === scenario)!;
    const id = scenario === "raw" ? `web_${crypto.randomUUID().slice(0, 16)}` : null;
    beginRun(id);
    try {
      if (def.path === null) {
        finishRaw(await runRawIntent(rawForm, id!));
      } else {
        finishRun(await runSimulation(def.path, { instruction, budget: "100.00" }));
      }
    } catch (thrown) {
      failRun(
        isSimulatorError(thrown)
          ? thrown
          : { error: "REQUEST_FAILED", message: String((thrown as Error)?.message ?? thrown) },
      );
    }
  }, [scenario, rawForm, instruction, beginRun, finishRaw, finishRun, failRun, resetEvents]);

  const approve = useCallback(async () => {
    if (!run) return;
    try {
      finishRun(await approveRun(run.run_id));
    } catch (thrown) {
      failRun(
        isSimulatorError(thrown)
          ? thrown
          : { error: "APPROVAL_FAILED", message: String(thrown) },
      );
    }
  }, [run, finishRun, failRun]);

  const view = run ? fromRun(run) : rawDecision ? fromRaw(rawDecision) : null;

  return {
    ...store,
    rawForm,
    setRawForm,
    instruction,
    setInstruction,
    events,
    socketState,
    pipeline,
    busy,
    start,
    approve,
    view,
  };
}
