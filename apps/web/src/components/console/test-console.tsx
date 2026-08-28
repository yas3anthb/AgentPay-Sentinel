"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { DecisionCard, fromRaw, fromRun } from "@/components/console/decision-card";
import { ScenarioForm } from "@/components/console/scenario-form";
import { TranscriptPanel } from "@/components/console/transcript-panel";
import { StageList2D } from "@/components/pipeline/stage-list-2d";
import { PipelineStage } from "@/components/pipeline/pipeline-stage";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { isSimulatorError, type SimulatorError } from "@/lib/api/transcript";
import { reducePipeline } from "@/lib/pipeline";
import { approveRun, runRawIntent, runSimulation, type RawIntentForm } from "@/lib/run-scenario";
import { SCENARIOS, useConsole } from "@/lib/store";
import { usePrefersReducedMotion, useStageEvents } from "@/lib/use-stage-events";

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
    <div className="grid gap-4 xl:grid-cols-[330px_minmax(0,1fr)_400px]">
      <Panel className="flex flex-col">
        <PanelHeader
          title="Scenario"
          subtitle="Three run through the real CrewAI agent. The fourth bypasses it."
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
        <div className="mt-auto border-t border-hairline p-3">
          <Button onClick={start} disabled={busy} className="w-full" size="lg">
            {busy ? "running…" : "Run scenario"}
          </Button>
          <p className="mt-2 text-center font-mono text-[10px] text-chalk-faint">
            relay socket: {socketState}
          </p>
          {/* Screen readers get the outcome announced; the 3D scene is decorative to them. */}
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

      <div className="flex flex-col gap-4">
        <Panel className="min-h-[420px]">
          <PanelHeader
            title="Enforcement pipeline"
            subtitle="Driven by live stage events from the gateway — the timing you see is the timing that happened."
            actions={
              phase === "paused" ? <Badge tone="approval">paused — awaiting approval</Badge> : null
            }
          />
          <PipelineStage state={pipeline} reducedMotion={reducedMotion} phase={phase} />
        </Panel>

        <Panel>
          <PanelHeader title="Stages" subtitle="The same data, as a list." />
          <div className="p-3">
            <StageList2D state={pipeline} reducedMotion={reducedMotion} />
          </div>
        </Panel>
      </div>

      <div className="flex min-h-0 flex-col gap-4">
        <Panel className="flex min-h-[300px] flex-col">
          <PanelHeader
            title="Agent transcript"
            subtitle={
              run
                ? `${run.transcript.steps.length} steps · ${run.scenario}`
                : "Run a scenario to see the agent's tool calls and reasoning steps."
            }
          />
          {error ? <ErrorPanel error={error} /> : null}
          {run ? (
            <TranscriptPanel run={run} reducedMotion={reducedMotion} />
          ) : !error ? (
            <p className="p-4 text-[11px] text-chalk-faint">no run yet</p>
          ) : null}
        </Panel>

        {run?.injection ? <InjectionProof injection={run.injection} /> : null}

        {phase === "paused" && run ? (
          <Panel>
            <PanelHeader
              title="Human approval required"
              subtitle="The graph is stopped on an interrupt. Nothing is polling; it resumes only when you act."
            />
            <div className="flex gap-2 p-4">
              <Button variant="approve" onClick={approve} className="flex-1">
                Approve
              </Button>
              <Button
                variant="danger"
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
          </Panel>
        ) : null}
      </div>
    </div>
  );
}

function ErrorPanel({ error }: { error: SimulatorError }) {
  return (
    <div className="m-3 rounded border border-signal-block/50 bg-signal-block/[0.07] p-3">
      <div className="flex items-center gap-2">
        <Badge tone="block">{error.error}</Badge>
        <span className="font-mono text-[10px] uppercase tracking-wider text-chalk-faint">
          run failed
        </span>
      </div>
      <p className="mt-2 whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-chalk-muted">
        {error.message}
      </p>
      <p className="mt-2 text-[10px] leading-relaxed text-chalk-faint">
        No transcript is shown because no run happened. The simulator returns an error rather
        than a plausible-looking sequence of steps.
      </p>
    </div>
  );
}

function InjectionProof({
  injection,
}: {
  injection: { payload_sha256: string; payload_chars: number; reached_agent_unmodified: boolean };
}) {
  return (
    <Panel>
      <PanelHeader
        title="Injection integrity"
        subtitle="Whether the attack reached the agent intact. A block only proves something if nothing upstream sanitised it first."
      />
      <div className="flex flex-col gap-2 p-4">
        <div className="flex items-center gap-2">
          <Badge tone={injection.reached_agent_unmodified ? "block" : "neutral"}>
            {injection.reached_agent_unmodified ? "reached agent unmodified" : "payload altered"}
          </Badge>
          <span className="font-mono text-[10px] text-chalk-faint">
            {injection.payload_chars} chars
          </span>
        </div>
        <code className="break-all font-mono text-[10px] leading-relaxed text-chalk-muted">
          {injection.payload_sha256}
        </code>
        <p className="text-[10px] leading-relaxed text-chalk-faint">
          Neither CrewAI nor LangChain filtered the payload. The hash above matches the bytes
          recorded at the tool boundary, so the block happened at the gateway.
        </p>
      </div>
    </Panel>
  );
}
