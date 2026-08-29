"use client";

import { CheckCircle2, Clock, ShieldOff, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Field } from "@/components/ui/panel";
import type { CheckoutStep } from "@/lib/checkout-sandbox";
import type { RunPhase } from "@/lib/store";
import { shortHash } from "@/lib/utils";

interface OutcomeView {
  decision: string | null;
  state: string | null;
  paymentAuthorizationId: string | null;
  providerReference: string | null;
  auditHash: string | null;
  policyVersion: string | null;
}

type Headline = {
  icon: typeof CheckCircle2;
  tone: "allow" | "block" | "approval" | "neutral";
  title: string;
  note: string;
};

function headline(step: CheckoutStep, phase: RunPhase): Headline {
  if (step === "captured")
    return {
      icon: CheckCircle2,
      tone: "allow",
      title: "Payment captured",
      note: "Sentinel authorized the charge and the simulated rail settled it.",
    };
  if (step === "declined")
    return {
      icon: XCircle,
      tone: "block",
      title: "Payment declined",
      note: "The real authorization stage failed — the rail never captured.",
    };
  if (step === "not_reached")
    return {
      icon: ShieldOff,
      tone: "block",
      title: "Blocked before checkout",
      note: "Sentinel stopped the request. Razorpay was never contacted.",
    };
  if (phase === "paused")
    return {
      icon: Clock,
      tone: "approval",
      title: "Awaiting approval",
      note: "The order exists but nothing is charged until a human signs off.",
    };
  return {
    icon: Clock,
    tone: "neutral",
    title: "Processing",
    note: "Waiting on the Sentinel decision.",
  };
}

/**
 * A checkout confirmation, styled like a receipt — the payment-side facts
 * only. The Test Console owns the risk-signal breakdown and the consistency
 * check; this panel deliberately does not repeat them.
 */
export function CheckoutOutcome({
  view,
  step,
  phase,
  amount,
}: {
  view: OutcomeView | null;
  step: CheckoutStep;
  phase: RunPhase;
  amount: string | null;
}) {
  const h = headline(step, phase);
  const Icon = h.icon;

  return (
    <div className="flex flex-col">
      <div className="flex items-start gap-3 border-b border-line p-5">
        <Icon
          size={20}
          className={
            h.tone === "allow"
              ? "mt-0.5 shrink-0 text-allow"
              : h.tone === "block"
                ? "mt-0.5 shrink-0 text-block"
                : h.tone === "approval"
                  ? "mt-0.5 shrink-0 text-approval"
                  : "mt-0.5 shrink-0 text-ink-muted"
          }
        />
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-section text-ink">{h.title}</p>
            {view?.decision ? <Badge tone={h.tone}>{view.decision}</Badge> : null}
          </div>
          <p className="mt-1 text-caption text-ink-secondary">{h.note}</p>
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-4 p-5">
        {amount ? <Field label="Amount" value={amount} /> : null}
        <Field label="Rail status" value={view?.state ?? "—"} />
        <Field
          label="Payment authorization"
          mono
          value={view?.paymentAuthorizationId ?? "—"}
          title={view?.paymentAuthorizationId ?? undefined}
        />
        <Field
          label="Provider reference"
          mono
          value={view?.providerReference ?? "—"}
          title={view?.providerReference ?? undefined}
        />
        <Field label="Policy version" mono value={view?.policyVersion ?? "—"} />
        <Field
          label="Audit hash"
          mono
          value={view?.auditHash ? shortHash(view.auditHash, 18) : "—"}
          title={view?.auditHash ?? undefined}
        />
      </dl>
    </div>
  );
}
