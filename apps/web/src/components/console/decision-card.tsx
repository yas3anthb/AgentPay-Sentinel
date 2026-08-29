"use client";

import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
} from "recharts";

import { CheckCircle2, ShieldAlert } from "lucide-react";

import { Badge, decisionTone, DecisionPill } from "@/components/ui/badge";
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
  const chartColor = tone === "block" ? "#C2334A" : tone === "approval" ? "#9A5B00" : "#0F7A4E";
  const data = SIGNALS.map((signal) => ({
    signal: signal.label,
    value: Number(view.signals[signal.key] ?? 0),
    weight: signal.weight,
  }));

  return (
    <div className="flex flex-col gap-4 p-5">
      <div className="flex flex-wrap items-center gap-2">
        <DecisionPill decision={view.decision} className="px-2.5 py-1" />
        {view.state ? <Badge tone="neutral">{view.state}</Badge> : null}
        {view.policyVersion ? (
          <span className="font-mono text-data text-ink-muted">Policy {view.policyVersion}</span>
        ) : null}
      </div>

      {view.reasonCodes.length ? (
        <div className="flex flex-wrap gap-1.5">
          {view.reasonCodes.map((code) => (
            <Badge key={code} tone="neutral" className="font-mono normal-case tracking-normal">
              {code}
            </Badge>
          ))}
        </div>
      ) : null}

      {/* The classifier's real mode, read off this transaction rather than guessed. */}
      {view.classifierDegraded !== null ? (
        <div
          className={cn(
            "rounded-control border px-3 py-2.5 text-caption",
            view.classifierDegraded
              ? "border-notice-line bg-notice-tint text-notice"
              : "border-line bg-surface-sunken text-ink-secondary",
          )}
        >
          <span className="font-medium">
            {view.classifierDegraded ? "Content classifier degraded" : "Content classifier live"}
          </span>
          {" — "}
          {view.classifierDegraded
            ? "no classifier verdict for this transaction. It proceeded only because policy was configured to tolerate that."
            : "the injection classifier returned a verdict for this transaction."}
        </div>
      ) : null}

      {providerDelta !== null && providerDelta !== undefined ? (
        <ProviderDelta delta={providerDelta} emphasised={Boolean(isAdversarial)} />
      ) : null}

      <div className="grid grid-cols-2 gap-4">
        <Field label="Authorization ID" value={view.paymentAuthorizationId ?? "—"} mono />
        <Field label="Audit hash" value={shortHash(view.auditHash, 18)} mono />
      </div>

      <div>
        <div className="mb-1.5 flex items-baseline justify-between">
          <span className="label">Risk signals</span>
          <span className="text-caption text-ink">
            <span className="font-mono">{view.weightedScore ?? "—"}</span>
            <span className="text-ink-muted"> / 100</span>
          </span>
        </div>

        {/* The formula, stated once, so the final score is never a bare
            number — a technical reviewer can see exactly how it was derived. */}
        <p className="mb-2 overflow-x-auto whitespace-nowrap font-mono text-data text-ink-secondary">
          R = {SIGNALS.map((s) => `${s.weight}·${s.label}`).join(" + ")}
        </p>

        <div className="h-[190px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <RadarChart data={data} outerRadius="72%">
              <PolarGrid stroke="#E3E6EB" />
              <PolarAngleAxis
                dataKey="signal"
                tick={{ fill: "#5A6577", fontSize: 11, fontFamily: "var(--font-inter)" }}
              />
              <PolarRadiusAxis domain={[0, 1]} tick={false} axisLine={false} />
              <Radar
                dataKey="value"
                stroke={chartColor}
                fill={chartColor}
                fillOpacity={0.14}
                strokeWidth={1.5}
                isAnimationActive={false}
              />
            </RadarChart>
          </ResponsiveContainer>
        </div>

        {/* The arithmetic, connected: value × weight = contribution, summed to
            the score shown above — not two disconnected facts. */}
        <div className="mt-1 overflow-x-auto">
          <table className="w-full min-w-[420px] border-collapse text-center">
            <thead>
              <tr className="border-b border-line">
                <th className="label px-1 py-1 text-left font-medium">Signal</th>
                {data.map((d) => (
                  <th key={d.signal} className="label px-1 py-1 font-medium">
                    {d.signal}
                  </th>
                ))}
                <th className="label px-1 py-1 font-medium text-ink">= R</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-line">
                <td className="px-1 py-1.5 text-left text-label text-ink-muted">Value</td>
                {data.map((d) => (
                  <td key={d.signal} className="px-1 py-1.5 font-mono text-data tabular-nums text-ink">
                    {d.value.toFixed(2)}
                  </td>
                ))}
                <td rowSpan={3} className="px-1 py-1.5 align-middle font-mono text-section tabular-nums text-ink">
                  {view.weightedScore ?? "—"}
                </td>
              </tr>
              <tr className="border-b border-line">
                <td className="px-1 py-1.5 text-left text-label text-ink-muted">Weight</td>
                {data.map((d) => (
                  <td key={d.signal} className="px-1 py-1.5 font-mono text-data tabular-nums text-ink-secondary">
                    ×{d.weight}%
                  </td>
                ))}
              </tr>
              <tr>
                <td className="px-1 py-1.5 text-left text-label text-ink-muted">Contribution</td>
                {data.map((d) => (
                  <td key={d.signal} className="px-1 py-1.5 font-mono text-data tabular-nums text-accent">
                    {(d.value * d.weight).toFixed(1)}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
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
  const Icon = contained ? CheckCircle2 : ShieldAlert;
  return (
    <div
      className={cn(
        "rounded-control border px-3.5 py-3",
        contained && emphasised
          ? "border-allow-line bg-allow-tint"
          : !contained && emphasised
            ? "border-block-line bg-block-tint"
            : "border-line bg-surface-sunken",
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Icon
            size={16}
            className={contained && emphasised ? "text-allow" : !contained && emphasised ? "text-block" : "text-ink-muted"}
          />
          <span className="label">Payment provider calls</span>
        </div>
        <span
          className={cn(
            "font-mono text-section tabular-nums",
            contained && emphasised ? "text-allow" : !contained && emphasised ? "text-block" : "text-ink",
          )}
        >
          {delta}
        </span>
      </div>
      {emphasised ? (
        <p className="mt-1.5 text-caption text-ink-secondary">
          {contained
            ? "The provider was never contacted. The block happened before any token existed, so there was no credential that could have reached it."
            : "The provider WAS contacted on a blocked run — containment failure."}
        </p>
      ) : null}
    </div>
  );
}
