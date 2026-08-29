"use client";

import { AlertTriangle, Fingerprint } from "lucide-react";

import { ConsistencyCheck } from "@/components/console/consistency-check";
import { DecisionCard } from "@/components/console/decision-card";
import { ScenarioForm } from "@/components/console/scenario-form";
import { TranscriptPanel } from "@/components/console/transcript-panel";
import { StagesTable } from "@/components/pipeline/stages-table";
import { PipelineStage } from "@/components/pipeline/pipeline-stage";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { type SimulatorError } from "@/lib/api/transcript";
import { useConsole } from "@/lib/store";
import { useScenarioRunner } from "@/lib/use-scenario-runner";
import { usePrefersReducedMotion } from "@/lib/use-stage-events";
import { shortHash } from "@/lib/utils";

export function TestConsole() {
  const {
    scenario,
    phase,
    run,
    error,
    setScenario,
    rawForm,
    setRawForm,
    instruction,
    setInstruction,
    socketState,
    pipeline,
    busy,
    start,
    approve,
    view,
  } = useScenarioRunner();

  const reducedMotion = usePrefersReducedMotion();

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
