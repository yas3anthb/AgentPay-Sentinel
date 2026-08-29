"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Fingerprint } from "lucide-react";

import { ConsistencyCheck } from "@/components/console/consistency-check";
import { DecisionCard, fromRaw, fromRun } from "@/components/console/decision-card";
import { ScenarioForm } from "@/components/console/scenario-form";
import { TranscriptPanel } from "@/components/console/transcript-panel";
import { StagesTable } from "@/components/pipeline/stages-table";
import { PipelineStage } from "@/components/pipeline/pipeline-stage";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { isSimulatorError, type SimulatorError } from "@/lib/api/transcript";
import { reducePipeline } from "@/lib/pipeline";
import { approveRun, runRawIntent, runSimulation, type RawIntentForm } from "@/lib/run-scenario";
import { SCENARIOS, useConsole } from "@/lib/store";
import { usePrefersReducedMotion, useStageEvents } from "@/lib/use-stage-events";
import { shortHash } from "@/lib/utils";

const DEFAULT_RAW: RawIntentForm = {
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

export function TestConsole() {
  const {
    scenario,
    phase,
    requestId,
    run,
    rawDecision,
    error,
    setScenario,
    beginRun,
    setEvents,
    finishRun,
    finishRaw,
    failRun,
  } = useConsole();

  const reducedMotion = usePrefersReducedMotion();
  const [rawForm, setRawForm] = useState<RawIntentForm>(DEFAULT_RAW);
  const [instruction, setInstruction] = useState(
    "Restock the office kitchen with coffee, keep it under $100.",
  );

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

  return (
    <div className="grid gap-5 xl:grid-cols-[330px_minmax(0,1fr)_400px]">
      <Panel className="flex flex-col">
        <PanelHeader
          title="Scenario"
          subtitle="Pick what the agent should try to do."
        />
        <ScenarioForm
          scenario={scenario}
          onScenario={setScenario}
          instruction={instruction}
          onInstruction={setInstruction}
          raw={rawForm}
          onRaw={setRawForm}
          disabled={busy}
        />
        <div className="mt-auto border-t border-line p-4">
          <Button onClick={start} disabled={busy} variant="primary" className="w-full" size="lg">
            {busy ? "Running…" : "Run scenario"}
          </Button>
          <p className="mt-2 text-center text-label text-ink-muted">
            Live updates: {socketState === "open" ? "connected" : socketState}
          </p>
          {/* Screen readers get the outcome announced; the visualisation is decorative to them. */}
          <p aria-live="polite" className="sr-only">
            {phase === "running"
              ? "Running scenario."
              : phase === "paused"
                ? "Paused, awaiting human approval."
                : phase === "error"
                  ? `Run failed: ${error?.error ?? "unknown error"}.`
                  : view
                    ? `Decision: ${view.decision}. Reasons: ${view.reasonCodes.join(", ")}.`
                    : ""}
          </p>
        </div>
      </Panel>

      <div className="flex flex-col gap-5">
        <Panel className="overflow-hidden">
          <PanelHeader
            title="Enforcement pipeline"
            subtitle="Reflects real timing from the gateway as it happens."
            actions={
              phase === "paused" ? <Badge tone="approval">Paused — awaiting approval</Badge> : null
            }
          />
          <PipelineStage state={pipeline} reducedMotion={reducedMotion} phase={phase} />
        </Panel>

        <Panel>
          <PanelHeader title="Stage detail" subtitle="What each step checked, and how long it took." />
          <StagesTable state={pipeline} />
        </Panel>
      </div>

      <div className="flex min-h-0 flex-col gap-5">
        <Panel className="flex min-h-[300px] flex-col">
          <PanelHeader
            title="Agent activity"
            subtitle={
              run
                ? `${run.transcript.steps.length} steps recorded`
                : "Run a scenario to see the agent's actions."
            }
          />
          {error ? <ErrorPanel error={error} /> : null}
          {run ? (
            <TranscriptPanel run={run} reducedMotion={reducedMotion} />
          ) : !error ? (
            <p className="p-4 text-caption text-ink-muted">No run yet.</p>
          ) : null}
        </Panel>

        {run?.injection ? <InjectionProof injection={run.injection} /> : null}

        {phase === "paused" && run ? (
          <Panel>
            <PanelHeader
              title="Waiting for your approval"
              subtitle="The agent has stopped and is not retrying or polling. Nothing proceeds until you decide."
            />
            <div className="flex gap-2 p-4">
              <Button variant="approve" onClick={approve} className="flex-1">
                Approve
              </Button>
              <Button
                variant="destructive"
                className="flex-1"
                onClick={() => useConsole.getState().reset()}
              >
                Deny
              </Button>
            </div>
          </Panel>
        ) : null}

        {view ? (
          <Panel>
            <PanelHeader title="Sentinel decision" />
            <DecisionCard
              view={view}
              providerDelta={run?.provider_calls.delta ?? null}
              isAdversarial={scenario === "adversarial"}
            />
            <div className="px-5 pb-5">
              <ConsistencyCheck
                state={pipeline}
                providerDelta={run?.provider_calls.delta}
                decision={view.decision}
              />
            </div>
          </Panel>
        ) : null}
      </div>
    </div>
  );
}

function ErrorPanel({ error }: { error: SimulatorError }) {
  return (
    <div className="m-4 flex items-start gap-2.5 rounded-panel border border-block-line bg-block-tint p-3.5">
      <AlertTriangle size={16} className="mt-0.5 shrink-0 text-block" />
      <div className="min-w-0">
        <p className="text-caption font-medium text-block">Run failed — {error.error}</p>
        <p className="mt-1 whitespace-pre-wrap break-words text-caption text-ink-secondary">
          {error.message}
        </p>
        <p className="mt-1.5 text-label text-ink-muted">
          No transcript is shown because no run happened.
        </p>
      </div>
    </div>
  );
}

function InjectionProof({
  injection,
}: {
  injection: { payload_sha256: string; payload_chars: number; reached_agent_unmodified: boolean };
}) {
  const known = injection.reached_agent_unmodified;
  return (
    <Panel>
      <PanelHeader
        title="Injection integrity"
        subtitle="Confirms the attack reached the agent unchanged before Sentinel blocked it."
      />
      <div className={known ? "flex gap-3 p-5" : "flex gap-3 border-t border-line p-5"}>
        <Fingerprint size={18} className={known ? "mt-0.5 shrink-0 text-block" : "mt-0.5 shrink-0 text-ink-muted"} />
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Badge tone={known ? "block" : "neutral"}>
              {known ? "Reached agent unmodified" : "Content altered before reaching agent"}
            </Badge>
            <span className="text-label text-ink-muted">{injection.payload_chars} characters</span>
          </div>
          <p className="mt-1.5 text-label text-ink-muted">Content hash (SHA-256)</p>
          <code className="block break-all font-mono text-data text-ink-secondary">
            {shortHash(injection.payload_sha256, 64)}
          </code>
          <p className="mt-1.5 text-caption text-ink-secondary">
            Neither the agent framework filtered this content. The block happened at the
            gateway, on the unmodified attack.
          </p>
        </div>
      </div>
    </Panel>
  );
}
