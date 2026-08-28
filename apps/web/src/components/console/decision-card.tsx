"use client";

import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
} from "recharts";

import { Badge, decisionTone } from "@/components/ui/badge";
import { Field } from "@/components/ui/panel";
import type { RunSummary } from "@/lib/api/transcript";
import type { DecisionResponse } from "@/lib/api/gateway";
import { cn, shortHash } from "@/lib/utils";

/** The five weighted risk signals, with the weights the engine actually uses. */
const SIGNALS: { key: string; label: string; weight: number }[] = [
  { key: "injection_confidence", label: "Injection", weight: 35 },
  { key: "policy_violation_score", label: "Policy", weight: 25 },
  { key: "budget_anomaly_score", label: "Budget", weight: 20 },
  { key: "merchant_risk_score", label: "Merchant", weight: 10 },
  { key: "velocity_risk_score", label: "Velocity", weight: 10 },
];

interface DecisionView {
  decision: string | null;
  reasonCodes: string[];
  policyVersion: string | null;
  state: string | null;
  signals: Record<string, unknown>;
  weightedScore: number | null;
  auditHash: string | null;
  paymentAuthorizationId: string | null;
  providerReference: string | null;
  classifierDegraded: boolean | null;
}

export function fromRun(run: RunSummary): DecisionView {
  const risk = run.sentinel.risk ?? {};
  const signals = (risk.signals ?? {}) as Record<string, unknown>;
  return {
    decision: run.decision,
    reasonCodes: run.reason_codes,
    policyVersion: run.sentinel.policy_version ?? null,
    state: run.sentinel.state ?? null,
    signals,
    weightedScore: typeof risk.weighted_score === "number" ? risk.weighted_score : null,
    auditHash: run.sentinel.audit_hash ?? null,
    paymentAuthorizationId: run.sentinel.payment_authorization_id ?? null,
    providerReference: run.sentinel.provider_reference ?? null,
    classifierDegraded:
      typeof signals.classifier_degraded === "boolean" ? signals.classifier_degraded : null,
  };
}

export function fromRaw(decision: DecisionResponse): DecisionView {
  const signals = decision.risk.signals as unknown as Record<string, unknown>;
  return {
    decision: decision.decision,
    reasonCodes: decision.reason_codes,
    policyVersion: decision.policy_version,
    state: decision.state,
    signals,
    weightedScore: decision.risk.weighted_score,
    auditHash: decision.audit_hash ?? null,
    paymentAuthorizationId: decision.payment_authorization_id,
    providerReference: decision.provider_reference ?? null,
    classifierDegraded:
      typeof signals.classifier_degraded === "boolean" ? signals.classifier_degraded : null,
  };
}

export function DecisionCard({
  view,
  providerDelta,
  isAdversarial,
}: {
  view: DecisionView;
  providerDelta?: number | null;
  isAdversarial?: boolean;
}) {
  const tone = decisionTone(view.decision);
  const data = SIGNALS.map((signal) => ({
    signal: signal.label,
    value: Number(view.signals[signal.key] ?? 0),
    weight: signal.weight,
  }));

  return (
    <div className="flex flex-col gap-3 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={tone} className="px-2 py-1 text-[11px]">
          {view.decision ?? "no decision"}
        </Badge>
        {view.state ? <Badge tone="neutral">{view.state}</Badge> : null}
        {view.policyVersion ? (
          <span className="font-mono text-[10px] text-chalk-faint">
            policy {view.policyVersion}
          </span>
        ) : null}
      </div>

      <div className="flex flex-wrap gap-1.5">
        {view.reasonCodes.map((code) => (
          <Badge key={code} tone={tone}>
            {code}
          </Badge>
        ))}
      </div>

      {/* The classifier's real mode, read off this transaction rather than guessed. */}
      {view.classifierDegraded !== null ? (
        <div
          className={cn(
            "rounded border px-3 py-2 text-[11px] leading-relaxed",
            view.classifierDegraded
              ? "border-signal-approval/40 bg-signal-approval/[0.07] text-chalk-muted"
              : "border-hairline bg-ink/50 text-chalk-faint",
          )}
        >
          <span className="font-mono uppercase tracking-wider">
            classifier {view.classifierDegraded ? "degraded" : "live"}
          </span>
          {" — "}
          {view.classifierDegraded
            ? "no classifier verdict for this transaction. It proceeded only because the policy was configured to tolerate that."
            : "the injection classifier returned a verdict for this transaction."}
        </div>
      ) : null}

      {providerDelta !== null && providerDelta !== undefined ? (
        <ProviderDelta delta={providerDelta} emphasised={Boolean(isAdversarial)} />
      ) : null}

      <div className="grid grid-cols-2 gap-3">
        <Field label="authorization id" value={view.paymentAuthorizationId ?? "—"} />
        <Field label="audit hash" value={shortHash(view.auditHash, 18)} />
      </div>

      <div>
        <div className="mb-1 flex items-baseline justify-between">
          <span className="label-xs">risk signals</span>
          <span className="font-mono text-[11px] text-chalk">
            {view.weightedScore ?? "—"}
            <span className="text-chalk-faint"> / 100</span>
          </span>
        </div>
        <div className="h-[190px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <RadarChart data={data} outerRadius="72%">
              <PolarGrid stroke="#1A2430" />
              <PolarAngleAxis
                dataKey="signal"
                tick={{ fill: "#6B7C8E", fontSize: 9, fontFamily: "var(--font-geist-mono)" }}
              />
              <PolarRadiusAxis domain={[0, 1]} tick={false} axisLine={false} />
              <Radar
                dataKey="value"
                stroke={tone === "block" ? "#F2637A" : tone === "approval" ? "#E0A340" : "#4EC9C0"}
                fill={tone === "block" ? "#F2637A" : tone === "approval" ? "#E0A340" : "#4EC9C0"}
                fillOpacity={0.18}
                strokeWidth={1.4}
                isAnimationActive={false}
              />
            </RadarChart>
          </ResponsiveContainer>
        </div>
        <ul className="mt-1 grid grid-cols-5 gap-1">
          {data.map((d) => (
            <li key={d.signal} className="text-center">
              <div className="font-mono text-[10px] tabular-nums text-chalk">
                {d.value.toFixed(2)}
              </div>
              <div className="font-mono text-[8px] uppercase tracking-wide text-chalk-faint">
                {d.signal} · {d.weight}%
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/**
 * The line that proves containment. Read from the mock provider's own counter,
 * not inferred from the gateway's side of the conversation.
 */
function ProviderDelta({ delta, emphasised }: { delta: number; emphasised: boolean }) {
  const contained = delta === 0;
  return (
    <div
      className={cn(
        "rounded border px-3 py-2.5",
        contained && emphasised
          ? "border-signal-allow/50 bg-signal-allow/[0.08]"
          : "border-hairline bg-ink/50",
        !contained && emphasised && "border-signal-block/50 bg-signal-block/[0.08]",
      )}
    >
      <div className="flex items-baseline justify-between gap-3">
        <span className="label-xs">payment provider calls</span>
        <span
          className={cn(
            "font-mono text-lg tabular-nums leading-none",
            contained ? "text-signal-allow" : "text-chalk",
          )}
        >
          {delta}
        </span>
      </div>
      {emphasised ? (
        <p className="mt-1.5 text-[11px] leading-relaxed text-chalk-muted">
          {contained
            ? "The provider was never contacted. The block happened before any token existed, so there was no credential that could have reached it."
            : "The provider WAS contacted on a blocked run — containment failure."}
        </p>
      ) : null}
    </div>
  );
}
