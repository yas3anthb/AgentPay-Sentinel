"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ShieldAlert, ShieldCheck } from "lucide-react";

import { Badge, DecisionPill } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Panel, PanelHeader } from "@/components/ui/panel";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ConfigurationTab } from "@/components/agents/configuration-tab";
import {
  DEMO,
  fetchPolicy,
  fetchRevokedSet,
  fetchTransactions,
  reinstateDelegation,
  resetGatewayDemoState,
  revokeDelegation,
  type DelegationPolicy,
  type TransactionRow,
} from "@/lib/agents";
import { cn } from "@/lib/utils";

const POLL_MS = 2000;

export function AgentsView() {
  const [policy, setPolicy] = useState<DelegationPolicy | null>(null);
  const [revoked, setRevoked] = useState<string[]>([]);
  const [transactions, setTransactions] = useState<TransactionRow[]>([]);
  const [revokedAt, setRevokedAt] = useState<number | null>(null);
  const [observedAfterMs, setObservedAfterMs] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const isRevoked = revoked.includes(DEMO.delegationId) || policy?.revoked === true;

  const refresh = useCallback(async () => {
    const [p, r, t] = await Promise.all([
      fetchPolicy(DEMO.delegationId),
      fetchRevokedSet(),
      fetchTransactions(25),
    ]);
    setPolicy(p);
    setRevoked(r);
    setTransactions(t);
    return r.includes(DEMO.delegationId);
  }, []);

  useEffect(() => {
    void refresh();
    const id = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  // Measures how long it actually took for the revocation to become visible
  // here. The README calls this near-real-time, not instant, so the UI shows
  // the real number rather than flipping the badge optimistically.
  useEffect(() => {
    if (revokedAt === null || observedAfterMs !== null) return;
    if (isRevoked) setObservedAfterMs(Date.now() - revokedAt);
  }, [isRevoked, revokedAt, observedAfterMs]);

  const agentTransactions = useMemo(
    () => transactions.filter((t) => t.agent_id === DEMO.agentId),
    [transactions],
  );

  const doRevoke = async () => {
    setBusy(true);
    setObservedAfterMs(null);
    setRevokedAt(Date.now());
    try {
      await revokeDelegation(DEMO.delegationId);
      setNotice("Revocation written. Watching for it to take effect…");
    } catch (error) {
      setNotice(String(error));
      setRevokedAt(null);
    } finally {
      setBusy(false);
    }
  };

  const doReinstate = async () => {
    setBusy(true);
    try {
      await reinstateDelegation(DEMO.delegationId);
      setRevokedAt(null);
      setObservedAfterMs(null);
      setNotice("Delegation reinstated.");
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const doReset = async () => {
    setBusy(true);
    try {
      const result = await resetGatewayDemoState();
      setNotice(`Demo state cleared (${JSON.stringify(result)}).`);
      await refresh();
    } catch (error) {
      setNotice(String(error));
    } finally {
      setBusy(false);
      setConfirmReset(false);
    }
  };

  return (
    <Tabs defaultValue="overview" className="flex flex-col gap-5">
      <TabsList>
        <TabsTrigger value="overview">Overview</TabsTrigger>
        <TabsTrigger value="configuration">Configuration</TabsTrigger>
      </TabsList>

      <TabsContent value="overview">
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
          <div className="flex flex-col gap-5">
        <Panel>
          <PanelHeader
            title="Registered agent"
            subtitle="Delegated authority, as the system holds it."
            actions={
              <Badge tone={isRevoked ? "block" : "allow"}>
                {isRevoked ? "Revoked" : "Active"}
              </Badge>
            }
          />
          <div className="grid grid-cols-2 gap-4 p-5">
            <Field label="Agent" value={DEMO.agentId} mono />
            <Field label="Owner" value={DEMO.userId} mono />
            <Field label="Delegation" value={DEMO.delegationId} mono />
            <Field label="Scopes" value="payments:authorize" mono />
            <Field
              label="Per transaction"
              value={policy ? `${policy.per_transaction_limit} ${policy.currency}` : "—"}
            />
            <Field label="Daily" value={policy ? `${policy.daily_limit} ${policy.currency}` : "—"} />
            <Field
              label="Approval over"
              value={policy ? `${policy.approval_threshold} ${policy.currency}` : "—"}
            />
            <Field label="Policy" value={policy?.policy_version ?? "—"} mono />
            <Field
              label="Last transaction"
              value={
                agentTransactions[0]
                  ? new Date(agentTransactions[0].created_at).toLocaleTimeString()
                  : "None yet"
              }
            />
            <Field
              label="Per-hour cap"
              value={policy ? String(policy.max_transactions_per_hour) : "—"}
            />
          </div>
        </Panel>

        <Panel>
          <PanelHeader title="Delegation chain" subtitle="Who authorised what." />
          <div className="flex flex-wrap items-center gap-2 p-5">
            <Chain label={DEMO.userId} tone="neutral" />
            <Arrow />
            <Chain label={DEMO.delegationId} tone={isRevoked ? "block" : "neutral"} />
            <Arrow />
            <Chain label={DEMO.agentId} tone="neutral" />
            <Arrow />
            <Chain label="payments:authorize" tone={isRevoked ? "block" : "allow"} />
          </div>
        </Panel>

        <Panel>
          <PanelHeader
            title="Revocation"
            subtitle="The delegation stays cryptographically valid until it expires. Revoking it takes effect once the change propagates — this is near-real-time, not instant."
          />
          <div className="flex flex-col gap-3.5 p-5">
            <div className="flex gap-2">
              <Button variant="destructive" onClick={doRevoke} disabled={busy || isRevoked}>
                Revoke delegation
              </Button>
              <Button variant="secondary" onClick={doReinstate} disabled={busy || !isRevoked}>
                Reinstate
              </Button>
            </div>

            {revokedAt !== null ? (
              <div className="rounded-control border border-line bg-surface-sunken px-3.5 py-3">
                <div className="label">Observed propagation time</div>
                <div className="mt-1 font-mono text-section tabular-nums text-ink">
                  {observedAfterMs === null ? (
                    <span className="animate-pulse-soft text-ink-muted">Waiting…</span>
                  ) : (
                    <>
                      {observedAfterMs}
                      <span className="text-caption text-ink-muted">ms</span>
                    </>
                  )}
                </div>
                <p className="mt-1.5 text-caption text-ink-secondary">
                  Measured from the revoke call to this page seeing it, polling every{" "}
                  {POLL_MS}ms. The number above includes that polling interval rather than an
                  optimistic instant flip.
                </p>
              </div>
            ) : null}

            {notice ? <p className="text-caption text-ink-secondary">{notice}</p> : null}
          </div>
        </Panel>

        <Panel className="border-approval-line">
          <PanelHeader
            title="Reset demo state"
            subtitle="Dev-only. Clears every transaction and the audit chain — including the duplicate-purchase check and daily budget a demo in progress may depend on."
            actions={<Badge tone="approval">Destructive</Badge>}
          />
          <div className="p-5">
            {confirmReset ? (
              <div className="flex flex-col gap-3">
                <p className="text-caption text-ink-secondary">
                  This clears the audit chain and every transaction. If someone is mid-demo,
                  their duplicate-purchase and budget state goes with it. Continue?
                </p>
                <div className="flex gap-2">
                  <Button variant="destructive" onClick={doReset} disabled={busy}>
                    Yes, clear it
                  </Button>
                  <Button variant="ghost" onClick={() => setConfirmReset(false)}>
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <Button variant="secondary" onClick={() => setConfirmReset(true)}>
                Reset demo state…
              </Button>
            )}
          </div>
        </Panel>
      </div>

      <Panel className="flex min-h-0 flex-col">
        <PanelHeader
          title="Recent transactions"
          subtitle={`${agentTransactions.length} for this agent · refreshing every ${POLL_MS / 1000}s`}
        />
        <div className="max-h-[76vh] overflow-y-auto">
          <table className="w-full border-collapse text-left">
            <thead className="sticky top-0 bg-surface">
              <tr className="border-b border-line">
                {["Time", "Merchant", "Amount", "Decision", "State", "Reasons"].map((h) => (
                  <th key={h} className="label px-4 py-2.5 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {agentTransactions.map((row) => (
                <tr key={row.payment_authorization_id} className="border-b border-line">
                  <td className="whitespace-nowrap px-4 py-2.5 font-mono text-data text-ink-muted">
                    {new Date(row.created_at).toLocaleTimeString()}
                  </td>
                  <td className="px-4 py-2.5 text-caption text-ink">{row.merchant_id}</td>
                  <td className="whitespace-nowrap px-4 py-2.5 font-mono text-data tabular-nums text-ink">
                    {row.amount} {row.currency}
                  </td>
                  <td className="px-4 py-2.5">
                    <DecisionPill decision={row.decision} />
                  </td>
                  <td className="px-4 py-2.5 text-caption text-ink-secondary">{row.state}</td>
                  <td className="px-4 py-2.5">
                    <div className="flex flex-wrap gap-1.5">
                      {row.reason_codes.slice(0, 3).map((code) => (
                        <span
                          key={code}
                          className={cn(
                            "font-mono text-label normal-case tracking-normal",
                            row.decision === "BLOCK" ? "text-block" : "text-ink-muted",
                          )}
                        >
                          {code}
                        </span>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
              {agentTransactions.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-caption text-ink-muted">
                    No transactions yet
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
            </div>
          </Panel>
        </div>
      </TabsContent>

      <TabsContent value="configuration">
        <ConfigurationTab />
      </TabsContent>
    </Tabs>
  );
}

function Chain({
  label,
  tone,
}: {
  label: string;
  tone: "neutral" | "allow" | "block";
}) {
  const Icon = tone === "block" ? ShieldAlert : ShieldCheck;
  return (
    <Badge tone={tone} className="font-mono normal-case tracking-normal">
      <Icon size={11} />
      {label}
    </Badge>
  );
}

function Arrow() {
  return <span className="text-ink-muted">→</span>;
}
