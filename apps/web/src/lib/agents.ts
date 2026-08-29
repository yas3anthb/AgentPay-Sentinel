"use client";

import { gateway } from "@/lib/api/gateway";
import { GATEWAY_URL } from "@/lib/config";

/** The demo delegation. The gateway has no "list agents" endpoint, so the
 * control plane is read through the endpoints that do exist. */
export const DEMO = {
  userId: "user_ada",
  agentId: "agent_shopper_01",
  delegationId: "del_office_supplies",
};

export interface DelegationPolicy {
  delegation_id: string;
  user_id: string;
  agent_id: string;
  policy_version: string;
  per_transaction_limit: string;
  daily_limit: string;
  currency: string;
  approval_threshold: string;
  max_transactions_per_hour: number;
  require_verified_merchant: boolean;
  allowed_merchants: string[];
  blocked_merchants: string[];
  revoked: boolean;
}

export interface TransactionRow {
  payment_authorization_id: string;
  created_at: string;
  user_id: string;
  agent_id: string;
  merchant_id: string;
  amount: string;
  currency: string;
  decision: string;
  reason_codes: string[];
  state: string;
  weighted_score: number | null;
  policy_version: string;
}

function rec(v: unknown): Record<string, unknown> {
  return typeof v === "object" && v !== null ? (v as Record<string, unknown>) : {};
}

export async function fetchPolicy(delegationId: string): Promise<DelegationPolicy | null> {
  const response = await fetch(`${GATEWAY_URL}/v1/admin/policies/${delegationId}`, {
    cache: "no-store",
  });
  if (!response.ok) return null;
  const raw = rec(await response.json());
  return {
    delegation_id: String(raw.delegation_id ?? delegationId),
    user_id: String(raw.user_id ?? ""),
    agent_id: String(raw.agent_id ?? ""),
    policy_version: String(raw.policy_version ?? ""),
    per_transaction_limit: String(raw.per_transaction_limit ?? "0"),
    daily_limit: String(raw.daily_limit ?? "0"),
    currency: String(raw.currency ?? "USD"),
    approval_threshold: String(raw.approval_threshold ?? "0"),
    max_transactions_per_hour: Number(raw.max_transactions_per_hour ?? 0),
    require_verified_merchant: raw.require_verified_merchant === true,
    allowed_merchants: Array.isArray(raw.allowed_merchants) ? raw.allowed_merchants.map(String) : [],
    blocked_merchants: Array.isArray(raw.blocked_merchants) ? raw.blocked_merchants.map(String) : [],
    revoked: raw.revoked === true,
  };
}

export async function fetchRevokedSet(): Promise<string[]> {
  const { data } = await gateway.GET("/v1/admin/delegations/revoked", {});
  const revoked = rec(data).revoked;
  return Array.isArray(revoked) ? revoked.map(String) : [];
}

export async function fetchTransactions(limit = 50): Promise<TransactionRow[]> {
  const { data } = await gateway.GET("/v1/transactions", { params: { query: { limit } } });
  const rows = rec(data).transactions;
  return Array.isArray(rows) ? (rows as TransactionRow[]) : [];
}

export async function revokeDelegation(delegationId: string): Promise<void> {
  const response = await fetch(`${GATEWAY_URL}/v1/admin/delegations/${delegationId}/revoke`, {
    method: "POST",
  });
  if (!response.ok) throw new Error(`revoke failed: HTTP ${response.status}`);
}

export async function reinstateDelegation(delegationId: string): Promise<void> {
  await fetch(`${GATEWAY_URL}/v1/admin/delegations/${delegationId}/reinstate`, {
    method: "POST",
  });
}

export async function resetGatewayDemoState(): Promise<Record<string, unknown>> {
  const response = await fetch(`${GATEWAY_URL}/v1/admin/dev/reset`, { method: "POST" });
  if (!response.ok) throw new Error(`reset refused: HTTP ${response.status}`);
  return rec(await response.json());
}
