"use client";

import { GATEWAY_URL } from "@/lib/config";
import type { Decision } from "@/lib/api/gateway";

/** The exact shape `/v1/audit/events` returns, confirmed by inspecting a live
 * response — not assumed. Only the fields the explainer actually uses. */
export interface DecisionEvent {
  event_id: string;
  created_at: string;
  decision: Decision;
  reason_codes: string[];
  policy_version: string;
  risk: {
    signals: Record<string, number | boolean | string[]>;
    weighted_score: number;
  };
  payload: {
    merchant_id: string;
    amount: string;
    currency: string;
  };
}

export interface ExplainerRun {
  decision: Decision;
  reasonCodes: string[];
  weightedScore: number;
  policyVersion: string;
  merchant: string;
  amount: string;
  currency: string;
  /** Present only when this run came from a real audit event. */
  source: { eventId: string; occurredAt: string } | null;
}

/**
 * A representative example per branch, built from real audit events this
 * session actually produced against the live gateway (not invented numbers)
 * — used only when no live audit history exists yet for that branch.
 */
const REPRESENTATIVE: Record<Decision, ExplainerRun> = {
  ALLOW: {
    decision: "ALLOW",
    reasonCodes: ["POLICY_SATISFIED"],
    weightedScore: 4.4,
    policyVersion: "v1.4.2",
    merchant: "merch_beanery",
    amount: "63.75",
    currency: "USD",
    source: null,
  },
  REQUIRE_APPROVAL: {
    decision: "REQUIRE_APPROVAL",
    reasonCodes: ["ABOVE_APPROVAL_THRESHOLD"],
    weightedScore: 16.98,
    policyVersion: "v1.4.2",
    merchant: "merch_beanery",
    amount: "170.00",
    currency: "USD",
    source: null,
  },
  BLOCK: {
    decision: "BLOCK",
    reasonCodes: ["PROMPT_INJECTION_HIGH_CONFIDENCE"],
    weightedScore: 40.48,
    policyVersion: "v1.4.2",
    merchant: "merch_beanery",
    amount: "76.00",
    currency: "USD",
    source: null,
  },
};

function toRun(event: DecisionEvent): ExplainerRun {
  return {
    decision: event.decision,
    reasonCodes: event.reason_codes,
    weightedScore: event.risk.weighted_score,
    policyVersion: event.policy_version,
    merchant: event.payload.merchant_id,
    amount: event.payload.amount,
    currency: event.payload.currency,
    source: { eventId: event.event_id, occurredAt: event.created_at },
  };
}

/**
 * Finds the most recent real audit event for each branch. Falls back to the
 * representative example — built from real numbers this session measured,
 * but not from live history — only when nothing real is available yet.
 *
 * What this deliberately does NOT provide: per-stage timing. The gateway does
 * not persist stage-transition latencies (they are ephemeral Redis pub/sub,
 * consumed live by the relay); reusing a live audit event's finish time as if
 * it were a stage-by-stage measurement would be exactly the kind of
 * fabricated timing this explainer must not present as real.
 */
export async function loadExplainerRuns(): Promise<Record<Decision, ExplainerRun>> {
  try {
    const response = await fetch(`${GATEWAY_URL}/v1/audit/events?limit=200`, {
      cache: "no-store",
    });
    if (!response.ok) throw new Error(String(response.status));
    const body = (await response.json()) as { events?: DecisionEvent[] };
    const events = body.events ?? [];

    const runs = { ...REPRESENTATIVE };
    for (const decision of ["ALLOW", "REQUIRE_APPROVAL", "BLOCK"] as Decision[]) {
      const match = events.find((e) => e.decision === decision);
      if (match) runs[decision] = toRun(match);
    }
    return runs;
  } catch {
    return REPRESENTATIVE;
  }
}
