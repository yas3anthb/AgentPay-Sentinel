"use client";

import Link from "next/link";
import { AlertTriangle, ArrowRight, Info } from "lucide-react";

import { CheckoutOutcome } from "@/components/sandbox/checkout-outcome";
import { CheckoutPanel } from "@/components/sandbox/checkout-panel";
import { SentinelRibbon } from "@/components/sandbox/sentinel-ribbon";
import { ScenarioForm } from "@/components/console/scenario-form";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { useCheckoutSandbox } from "@/lib/checkout-sandbox";
import { type SimulatorError } from "@/lib/api/transcript";
import { useScenarioRunner } from "@/lib/use-scenario-runner";
import { usePrefersReducedMotion } from "@/lib/use-stage-events";

/**
 * The Sandbox answers one question the Test Console does not: "what does the
 * hand-off to a real payment rail look like once Sentinel says yes?"
 *
 * Everything that decides the outcome — identity, content analysis, risk
 * scoring, the OPA decision, the audit hash — is the same real gateway the
 * Test Console drives (shared via `useScenarioRunner`). This page keeps that
 * to a one-line ribbon and spends its space on the checkout instead.
 *
 * The checkout itself is explicitly simulated: no Razorpay API is called, no
 * Razorpay credentials exist anywhere in this app. It is driven entirely by
 * the real authorization stage (`useCheckoutSandbox`) — a block never reaches
 * it, a pause here is the same real approval pause, and captured vs declined
 * is read from the real settlement state, not invented.
 */
export function SandboxView() {
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
    pipeline,
    busy,
    start,
    view,
  } = useScenarioRunner();

  const reducedMotion = usePrefersReducedMotion();
  const checkoutStep = useCheckoutSandbox(pipeline, run);

  const amount =
    scenario === "raw"
      ? `${(Number(rawForm.amount) * rawForm.quantity).toFixed(2)} ${rawForm.currency}`
      : null;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start gap-2.5 rounded-panel border border-notice-line bg-notice-tint px-4 py-3">
        <Info size={16} className="mt-0.5 shrink-0 text-notice" />
        <div>
          <p className="text-caption font-medium text-notice">
            Simulated Razorpay checkout — not a live integration
          </p>
          <p className="mt-0.5 text-caption text-ink-secondary">
            No Razorpay API is called and no Razorpay credentials exist anywhere in this app. The
            decision is the real Sentinel gateway; only the payment hand-off below is a themed
            visualisation of what plugging in a real rail would look like.
          </p>
        </div>
      </div>

      <SentinelRibbon pipeline={pipeline} phase={phase} decision={view?.decision} />

      <div className="grid gap-5 xl:grid-cols-[320px_minmax(0,1fr)]">
        <Panel className="flex flex-col">
          <PanelHeader title="Scenario" subtitle="Pick what the agent should try to do." />
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
              {busy ? "Running…" : "Run checkout"}
            </Button>
            <Link
              href="/test"
              className="mt-3 flex items-center justify-center gap-1 text-label text-ink-muted hover:text-ink-secondary"
            >
              Full enforcement breakdown in the Test Console
              <ArrowRight size={12} />
            </Link>
          </div>
        </Panel>

        <div className="flex min-w-0 flex-col gap-5">
          <Panel className="overflow-hidden">
            <PanelHeader
              title="Razorpay checkout"
              subtitle="Plays out only when the real pipeline actually authorizes payment."
              actions={<Badge tone="accent">Simulated</Badge>}
            />
            <CheckoutPanel step={checkoutStep} reducedMotion={reducedMotion} />
          </Panel>

          {error ? (
            <Panel>
              <ErrorPanel error={error} />
            </Panel>
          ) : (
            <Panel className="overflow-hidden">
              <PanelHeader title="Checkout result" subtitle="The payment-side facts for this run." />
              <CheckoutOutcome view={view} step={checkoutStep} phase={phase} amount={amount} />
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}

function ErrorPanel({ error }: { error: SimulatorError }) {
  return (
    <div className="flex items-start gap-2.5 p-4">
      <AlertTriangle size={16} className="mt-0.5 shrink-0 text-block" />
      <div className="min-w-0">
        <p className="text-caption font-medium text-block">Run failed — {error.error}</p>
        <p className="mt-1 whitespace-pre-wrap break-words text-caption text-ink-secondary">
          {error.message}
        </p>
      </div>
    </div>
  );
}
