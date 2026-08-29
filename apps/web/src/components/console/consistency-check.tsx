"use client";

import { Badge } from "@/components/ui/badge";
import type { PipelineState } from "@/lib/pipeline";

/**
 * Cross-checks the two independent claims the console makes about a blocked
 * run, and says so loudly if they disagree:
 *
 *   1. the pipeline events say the authorization stage was never reached
 *      (token_issued: false, provider_contacted: false), which is what the
 *      severed beam draws;
 *   2. the mock provider's own call counter says its delta was 0.
 *
 * These come from different sources — Redis stage events versus the provider's
 * counter — so agreement is evidence rather than tautology. A contradiction
 * would mean the visualisation is lying about containment, which is the single
 * worst failure this UI could have, so it is surfaced rather than smoothed over.
 */
export function ConsistencyCheck({
  state,
  providerDelta,
  decision,
}: {
  state: PipelineState;
  providerDelta: number | null | undefined;
  decision: string | null;
}) {
  if (decision !== "BLOCK" || providerDelta === null || providerDelta === undefined) {
    return null;
  }

  const auth = state.authorization;
  const sawStageEvents = auth.status !== "idle";
  const stageSaysContained =
    auth.status === "skipped" ||
    auth.detail.provider_contacted === false ||
    auth.detail.never_reached === true;
  const counterSaysContained = providerDelta === 0;

  if (!sawStageEvents) {
    return (
      <Row tone="neutral" label="not cross-checked">
        The provider counter reported {providerDelta}, but no pipeline stage events were
        received for this run, so there is nothing to check it against.
      </Row>
    );
  }

  if (stageSaysContained && counterSaysContained) {
    return (
      <Row tone="allow" label="sources agree">
        The pipeline events say no token was issued and the provider was never contacted. The
        provider&apos;s own call counter independently reports 0. Two different sources, same
        answer.
      </Row>
    );
  }

  return (
    <Row tone="block" label="sources disagree">
      The pipeline events say the payment stage was{" "}
      <span className="font-mono">{auth.status}</span>, but the provider counter moved by{" "}
      {providerDelta}. One of these is wrong — do not trust the visualisation for this run.
    </Row>
  );
}

function Row({
  tone,
  label,
  children,
}: {
  tone: "allow" | "block" | "neutral";
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={
        tone === "block"
          ? "rounded border border-signal-block/60 bg-signal-block/[0.1] px-3 py-2.5"
          : tone === "allow"
            ? "rounded border border-hairline bg-ink/50 px-3 py-2.5"
            : "rounded border border-hairline bg-ink/50 px-3 py-2.5"
      }
    >
      <Badge tone={tone === "neutral" ? "neutral" : tone}>{label}</Badge>
      <p className="mt-1.5 text-[11px] leading-relaxed text-chalk-muted">{children}</p>
    </div>
  );
}
