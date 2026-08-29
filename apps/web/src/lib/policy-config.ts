"use client";

import { DEMO, type DelegationPolicy } from "@/lib/agents";
import { GATEWAY_URL, PROVIDER_ORIGIN_PROXY } from "@/lib/config";

/**
 * Every field here is checked, live, by the real `.rego` policy files —
 * confirmed by reading them, not assumed:
 *
 *   per_transaction_limit, daily_limit, currency   -> policies/spending.rego
 *   approval_threshold, max_transactions_per_hour  -> policies/spending.rego
 *   require_verified_merchant                      -> policies/merchant.rego
 *   allowed_merchants / blocked_merchants           -> policies/merchant.rego
 *
 * `context.py` reads these straight from Postgres on every single
 * transaction — there is no cache and no reload step, so a PUT through
 * these functions takes effect on the very next payment intent.
 *
 * Deliberately absent: any per-category dollar limit. `spending.rego` has
 * no such rule, and inventing one here would mean the UI claims to enforce
 * something the backend does not.
 */

export interface MerchantEntry {
  merchant_id: string;
  display_name: string;
  category: string;
  verified: boolean;
  risk_score: number;
}

function rec(v: unknown): Record<string, unknown> {
  return typeof v === "object" && v !== null ? (v as Record<string, unknown>) : {};
}

export async function fetchMerchants(): Promise<MerchantEntry[]> {
  const response = await fetch(`${GATEWAY_URL}/v1/admin/merchants`, { cache: "no-store" });
  if (!response.ok) return [];
  const merchants = rec(await response.json()).merchants;
  return Array.isArray(merchants) ? (merchants as MerchantEntry[]) : [];
}

/**
 * Spending/approval policy is a full upsert on the gateway (no PATCH), so the
 * only safe way to change one field is to fetch the complete current policy
 * first and send every field back — never guess at values this app didn't
 * just read, or a save could silently revert fields nobody meant to touch.
 */
export async function savePolicy(policy: DelegationPolicy): Promise<void> {
  const response = await fetch(`${GATEWAY_URL}/v1/admin/policies`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      delegation_id: policy.delegation_id,
      user_id: policy.user_id,
      agent_id: policy.agent_id,
      policy_version: policy.policy_version,
      per_transaction_limit: policy.per_transaction_limit,
      daily_limit: policy.daily_limit,
      currency: policy.currency,
      approval_threshold: policy.approval_threshold,
      max_transactions_per_hour: policy.max_transactions_per_hour,
      require_verified_merchant: policy.require_verified_merchant,
      allowed_merchants: policy.allowed_merchants,
      blocked_merchants: policy.blocked_merchants,
    }),
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`policy save failed: HTTP ${response.status} ${body.slice(0, 200)}`);
  }
}

/** Same full-upsert caution as `savePolicy`: every merchant field is
 * round-tripped from a real GET, never defaulted, before being sent back. */
export async function saveMerchant(merchant: MerchantEntry): Promise<void> {
  const response = await fetch(`${GATEWAY_URL}/v1/admin/merchants`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(merchant),
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`merchant save failed: HTTP ${response.status} ${body.slice(0, 200)}`);
  }
}

export async function registerMerchant(input: {
  merchant_id: string;
  display_name: string;
  category: string;
}): Promise<void> {
  await saveMerchant({ ...input, verified: false, risk_score: 0.5 });
}

export interface ProviderStatus {
  reachable: boolean;
  behaviour: string | null;
  detail: string;
}

/**
 * Read-only. There is no field anywhere in this module that accepts a
 * credential, a secret, or an API key — nor should there be. Connecting a
 * real payment provider is a backend deployment change (swap PROVIDER_URL,
 * redeploy), not something a browser form should ever mediate.
 */
export async function fetchProviderStatus(): Promise<ProviderStatus> {
  try {
    const response = await fetch(`${PROVIDER_ORIGIN_PROXY}/healthz`, { cache: "no-store" });
    if (!response.ok) return { reachable: false, behaviour: null, detail: `HTTP ${response.status}` };
    const body = rec(await response.json());
    return {
      reachable: body.status === "ok",
      behaviour: typeof body.behaviour === "string" ? body.behaviour : null,
      detail: "mock payment provider",
    };
  } catch (error) {
    return { reachable: false, behaviour: null, detail: String((error as Error).message ?? error) };
  }
}

export { DEMO };
