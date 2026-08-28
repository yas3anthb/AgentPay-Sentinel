"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge, decisionTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Panel, PanelHeader } from "@/components/ui/panel";
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
      setNotice("Revocation written. Watching for it to appear in the shared set…");
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
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
      <div className="flex flex-col gap-4">
        <Panel>
          <PanelHeader
            title="Registered agents"
            subtitle="Delegated authority, as the control plane holds it."
            actions={<Badge tone={isRevoked ? "block" : "allow"}>{isRevoked ? "revoked" : "active"}</Badge>}
          />
          <div className="grid grid-cols-2 gap-3 p-4">
            <Field label="agent" value={DEMO.agentId} />
            <Field label="owner" value={DEMO.userId} />
            <Field label="delegation" value={DEMO.delegationId} />
            <Field label="scopes" value="payments:authorize" />
            <Field
              label="per transaction"
              value={policy ? `${policy.per_transaction_limit} ${policy.currency}` : "—"}
            />
            <Field
              label="daily"
              value={policy ? `${policy.daily_limit} ${policy.currency}` : "—"}
            />
            <Field
              label="approval over"
              value={policy ? `${policy.approval_threshold} ${policy.currency}` : "—"}
            />
            <Field label="policy" value={policy?.policy_version ?? "—"} />
            <Field
              label="last transaction"
              value={
                agentTransactions[0]
                  ? new Date(agentTransactions[0].created_at).toLocaleTimeString()
                  : "none yet"
              }
            />
            <Field
              label="per hour cap"
              value={policy ? String(policy.max_transactions_per_hour) : "—"}
            />
          </div>
        </Panel>

        <Panel>
          <PanelHeader title="Delegation chain" subtitle="Who authorised what." />
          <div className="flex flex-wrap items-center gap-2 p-4 font-mono text-[11px]">
            <Chain label={DEMO.userId} tone="idle" />
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
            subtitle="The JWT stays cryptographically valid until it expires. The gateway rejects it anyway, once the revocation lands in the shared set."
          />
          <div className="flex flex-col gap-3 p-4">
            <div className="flex gap-2">
              <Button variant="danger" onClick={doRevoke} disabled={busy || isRevoked}>
                Revoke delegation
              </Button>
              <Button variant="outline" onClick={doReinstate} disabled={busy || !isRevoked}>
                Reinstate
              </Button>
            </div>

            {revokedAt !== null ? (
              <div className="rounded border border-hairline bg-ink/60 px-3 py-2.5">
                <div className="label-xs">observed propagation</div>
                <div className="mt-1 font-mono text-lg tabular-nums text-chalk">
                  {observedAfterMs === null ? (
                    <span className="text-signal-approval">waiting…</span>
                  ) : (
                    <>
                      {observedAfterMs}
                      <span className="text-sm text-chalk-faint">ms</span>
                    </>
                  )}
                </div>
                <p className="mt-1.5 text-[11px] leading-relaxed text-chalk-muted">
                  Measured from the revoke call to this page seeing it, polling every{" "}
                  {POLL_MS}ms. Near-real-time, not instant — the number above includes the
                  polling interval, and is shown rather than hidden behind an optimistic badge.
                </p>
              </div>
            ) : null}

            {notice ? (
              <p className="text-[11px] leading-relaxed text-chalk-muted">{notice}</p>
            ) : null}
          </div>
        </Panel>

        <Panel className="border-signal-approval/30">
          <PanelHeader
            title="Reset demo state"
            subtitle="Dev-only. Clears transactions, the audit chain, and the replay caches — including the duplicate fingerprints and rolling daily budget a demo in progress may depend on."
            actions={<Badge tone="approval">destructive</Badge>}
          />
          <div className="p-4">
            {confirmReset ? (
              <div className="flex flex-col gap-2">
                <p className="text-[11px] leading-relaxed text-chalk-muted">
                  This clears the audit chain and every transaction. If someone is mid-demo,
                  their fingerprint and budget state goes with it. Continue?
                </p>
                <div className="flex gap-2">
                  <Button variant="danger" onClick={doReset} disabled={busy}>
                    Yes, clear it
                  </Button>
                  <Button variant="ghost" onClick={() => setConfirmReset(false)}>
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <Button variant="outline" onClick={() => setConfirmReset(true)}>
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
            <thead className="sticky top-0 bg-ink-raised">
              <tr className="border-b border-hairline">
                {["time", "merchant", "amount", "decision", "state", "reasons"].map((h) => (
                  <th key={h} className="label-xs px-3 py-2 font-normal">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {agentTransactions.map((row) => (
                <tr key={row.payment_authorization_id} className="border-b border-hairline/60">
                  <td className="whitespace-nowrap px-3 py-2 font-mono text-[10px] text-chalk-faint">
                    {new Date(row.created_at).toLocaleTimeString()}
                  </td>
                  <td className="px-3 py-2 font-mono text-[11px] text-chalk">{row.merchant_id}</td>
                  <td className="whitespace-nowrap px-3 py-2 font-mono text-[11px] tabular-nums text-chalk">
                    {row.amount} {row.currency}
                  </td>
                  <td className="px-3 py-2">
                    <Badge tone={decisionTone(row.decision)}>{row.decision}</Badge>
                  </td>
                  <td className="px-3 py-2 font-mono text-[10px] text-chalk-muted">{row.state}</td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-1">
                      {row.reason_codes.slice(0, 3).map((code) => (
                        <span
                          key={code}
                          className={cn(
                            "font-mono text-[9px]",
                            row.decision === "BLOCK" ? "text-signal-block" : "text-chalk-faint",
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
                  <td colSpan={6} className="px-3 py-6 text-center text-[11px] text-chalk-faint">
                    no transactions yet
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}

function Chain({ label, tone }: { label: string; tone: "idle" | "neutral" | "allow" | "block" }) {
  return <Badge tone={tone}>{label}</Badge>;
}

function Arrow() {
  return <span className="text-chalk-faint">→</span>;
}
