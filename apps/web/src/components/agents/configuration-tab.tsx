"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Lock, Plus, ShieldOff, ShieldQuestion } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { DEMO, fetchPolicy, type DelegationPolicy } from "@/lib/agents";
import {
  fetchMerchants,
  fetchProviderStatus,
  registerMerchant,
  saveMerchant,
  savePolicy,
  type MerchantEntry,
  type ProviderStatus,
} from "@/lib/policy-config";
import { cn } from "@/lib/utils";

export function ConfigurationTab() {
  const [policy, setPolicy] = useState<DelegationPolicy | null>(null);
  const [merchants, setMerchants] = useState<MerchantEntry[]>([]);
  const [provider, setProvider] = useState<ProviderStatus | null>(null);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [p, m, prov] = await Promise.all([
      fetchPolicy(DEMO.delegationId),
      fetchMerchants(),
      fetchProviderStatus(),
    ]);
    setPolicy(p);
    setMerchants(m);
    setProvider(prov);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const saveField = async (patch: Partial<DelegationPolicy>) => {
    if (!policy) return;
    const next = { ...policy, ...patch };
    setPolicy(next);
    setSaving(true);
    try {
      await savePolicy(next);
      setNotice("Saved. Takes effect on the next payment intent — no reload needed.");
    } catch (error) {
      setNotice(String((error as Error).message ?? error));
    } finally {
      setSaving(false);
    }
  };

  const toggleList = async (merchantId: string, list: "allowed_merchants" | "blocked_merchants") => {
    if (!policy) return;
    const other = list === "allowed_merchants" ? "blocked_merchants" : "allowed_merchants";
    const inList = policy[list].includes(merchantId);
    await saveField({
      [list]: inList ? policy[list].filter((m) => m !== merchantId) : [...policy[list], merchantId],
      [other]: policy[other].filter((m) => m !== merchantId),
    } as Partial<DelegationPolicy>);
  };

  const toggleVerified = async (merchant: MerchantEntry) => {
    setSaving(true);
    try {
      await saveMerchant({ ...merchant, verified: !merchant.verified });
      setNotice(`${merchant.merchant_id} marked ${!merchant.verified ? "verified" : "unverified"}.`);
      await refresh();
    } catch (error) {
      setNotice(String((error as Error).message ?? error));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <Panel>
        <PanelHeader
          title="Spending & approval policy"
          subtitle="Every field below is checked live by policies/spending.rego on the very next payment — there is no separate reload step."
        />
        {policy ? (
          <SpendingForm policy={policy} onSave={saveField} disabled={saving} />
        ) : (
          <p className="p-5 text-caption text-ink-muted">Loading…</p>
        )}
      </Panel>

      <Panel>
        <PanelHeader
          title="Merchant allowlist, denylist & verification"
          subtitle="Allow/deny is scoped to this delegation (policies/merchant.rego). Verified status is on the shared merchant registry, so changing it affects every delegation."
        />
        <MerchantTable
          merchants={merchants}
          policy={policy}
          disabled={saving}
          onToggleList={toggleList}
          onToggleVerified={toggleVerified}
          onRegistered={refresh}
        />
      </Panel>

      <Panel>
        <PanelHeader
          title="Composite risk threshold"
          subtitle="Read-only. This number lives in policies/thresholds.rego, not the database — changing it means redeploying the policy bundle, not editing a form."
        />
        <div className="flex items-center gap-3 p-5">
          <Lock size={16} className="text-ink-muted" />
          <div>
            <p className="text-body text-ink">Composite score review threshold: 60 / 100</p>
            <p className="mt-1 text-caption text-ink-secondary">
              A transaction with no single hard failure but a weighted score at or above this
              routes to REQUIRE_APPROVAL. There is no admin endpoint that edits Rego constants —
              this is stated here rather than built as a form that would silently do nothing.
            </p>
          </div>
        </div>
      </Panel>

      <Panel>
        <PanelHeader
          title="Payment provider"
          subtitle="Read-only connection status. No credential entry — see the note below."
        />
        <div className="flex flex-col gap-3 p-5">
          <div className="flex items-center gap-3">
            <span
              className={cn(
                "h-2 w-2 rounded-full",
                provider?.reachable ? "bg-allow" : "bg-block",
              )}
            />
            <span className="text-body text-ink">Mock payment provider</span>
            <Badge tone={provider?.reachable ? "allow" : "block"}>
              {provider?.reachable ? "Reachable" : "Unreachable"}
            </Badge>
            {provider?.behaviour ? (
              <span className="font-mono text-data text-ink-muted">
                configured behaviour: {provider.behaviour}
              </span>
            ) : null}
          </div>
          <div className="flex items-start gap-2.5 rounded-control border border-notice-line bg-notice-tint p-3.5">
            <AlertTriangle size={15} className="mt-0.5 shrink-0 text-notice" />
            <p className="text-caption text-ink-secondary">
              This is a mock provider for demo and test purposes — never a place to paste live
              API keys or secrets into. Connecting a real payment provider means changing the
              gateway&apos;s <code className="font-mono">PROVIDER_URL</code> and redeploying the
              backend; it is a backend deployment change, not a browser form, and no UI in this
              product will ever ask for a live credential.
            </p>
          </div>
        </div>
      </Panel>

      {notice ? <p className="text-caption text-ink-secondary">{notice}</p> : null}
    </div>
  );
}

function SpendingForm({
  policy,
  onSave,
  disabled,
}: {
  policy: DelegationPolicy;
  onSave: (patch: Partial<DelegationPolicy>) => Promise<void>;
  disabled: boolean;
}) {
  const [draft, setDraft] = useState(policy);
  useEffect(() => setDraft(policy), [policy]);

  const dirty =
    draft.per_transaction_limit !== policy.per_transaction_limit ||
    draft.daily_limit !== policy.daily_limit ||
    draft.approval_threshold !== policy.approval_threshold ||
    draft.max_transactions_per_hour !== policy.max_transactions_per_hour ||
    draft.require_verified_merchant !== policy.require_verified_merchant;

  return (
    <div className="grid gap-4 p-5 sm:grid-cols-2">
      <MoneyField
        label="Per-transaction limit"
        rego="BUDGET_EXCEEDED"
        value={draft.per_transaction_limit}
        currency={draft.currency}
        onChange={(v) => setDraft({ ...draft, per_transaction_limit: v })}
        disabled={disabled}
      />
      <MoneyField
        label="Daily limit"
        rego="DAILY_BUDGET_EXCEEDED"
        value={draft.daily_limit}
        currency={draft.currency}
        onChange={(v) => setDraft({ ...draft, daily_limit: v })}
        disabled={disabled}
      />
      <MoneyField
        label="Approval threshold"
        rego="ABOVE_APPROVAL_THRESHOLD"
        value={draft.approval_threshold}
        currency={draft.currency}
        onChange={(v) => setDraft({ ...draft, approval_threshold: v })}
        disabled={disabled}
      />
      <label className="flex flex-col gap-1.5">
        <span className="label">
          Max transactions / hour{" "}
          <span className="normal-case font-normal text-ink-muted">— VELOCITY_LIMIT_EXCEEDED</span>
        </span>
        <input
          type="number"
          min={1}
          value={draft.max_transactions_per_hour}
          disabled={disabled}
          onChange={(e) =>
            setDraft({ ...draft, max_transactions_per_hour: Number(e.target.value) || 1 })
          }
          className="rounded-control border border-line-strong bg-surface px-3 py-2 text-body text-ink"
        />
      </label>

      <label className="flex items-center gap-2.5 sm:col-span-2">
        <input
          type="checkbox"
          checked={draft.require_verified_merchant}
          disabled={disabled}
          onChange={(e) => setDraft({ ...draft, require_verified_merchant: e.target.checked })}
          className="h-4 w-4 rounded border-line-strong accent-accent"
        />
        <span className="text-body text-ink">Require verified merchants</span>
        <span className="text-caption text-ink-muted">— UNVERIFIED_MERCHANT</span>
      </label>

      <div className="sm:col-span-2">
        <Button
          variant="primary"
          disabled={disabled || !dirty}
          onClick={() =>
            onSave({
              per_transaction_limit: draft.per_transaction_limit,
              daily_limit: draft.daily_limit,
              approval_threshold: draft.approval_threshold,
              max_transactions_per_hour: draft.max_transactions_per_hour,
              require_verified_merchant: draft.require_verified_merchant,
            })
          }
        >
          Save changes
        </Button>
      </div>
    </div>
  );
}

function MoneyField({
  label,
  rego,
  value,
  currency,
  onChange,
  disabled,
}: {
  label: string;
  rego: string;
  value: string;
  currency: string;
  onChange: (v: string) => void;
  disabled: boolean;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="label">
        {label} <span className="normal-case font-normal text-ink-muted">— {rego}</span>
      </span>
      <div className="flex items-center gap-2">
        <input
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          className="w-full rounded-control border border-line-strong bg-surface px-3 py-2 font-mono text-data text-ink"
        />
        <span className="text-caption text-ink-muted">{currency}</span>
      </div>
    </label>
  );
}

function MerchantTable({
  merchants,
  policy,
  disabled,
  onToggleList,
  onToggleVerified,
  onRegistered,
}: {
  merchants: MerchantEntry[];
  policy: DelegationPolicy | null;
  disabled: boolean;
  onToggleList: (id: string, list: "allowed_merchants" | "blocked_merchants") => Promise<void>;
  onToggleVerified: (m: MerchantEntry) => Promise<void>;
  onRegistered: () => Promise<void>;
}) {
  const [adding, setAdding] = useState(false);
  const [newId, setNewId] = useState("");
  const [newCategory, setNewCategory] = useState("retail");
  const [busy, setBusy] = useState(false);

  const register = async () => {
    if (!newId.trim()) return;
    setBusy(true);
    try {
      await registerMerchant({ merchant_id: newId.trim(), display_name: newId.trim(), category: newCategory });
      setNewId("");
      setAdding(false);
      await onRegistered();
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="border-b border-line">
              {["Merchant", "Category", "Verified", "Risk score", "This delegation"].map((h) => (
                <th key={h} className="label px-5 py-2.5 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {merchants.map((m) => {
              const allowed = policy?.allowed_merchants.includes(m.merchant_id);
              const blocked = policy?.blocked_merchants.includes(m.merchant_id);
              return (
                <tr key={m.merchant_id} className="border-b border-line">
                  <td className="px-5 py-2.5 font-mono text-data text-ink">{m.merchant_id}</td>
                  <td className="px-5 py-2.5 text-caption text-ink-secondary">{m.category}</td>
                  <td className="px-5 py-2.5">
                    <button
                      onClick={() => onToggleVerified(m)}
                      disabled={disabled}
                      className="inline-flex items-center gap-1.5"
                    >
                      {m.verified ? (
                        <Badge tone="allow">
                          <CheckCircle2 size={11} /> Verified
                        </Badge>
                      ) : (
                        <Badge tone="neutral">
                          <ShieldQuestion size={11} /> Unverified
                        </Badge>
                      )}
                    </button>
                  </td>
                  <td className="px-5 py-2.5 font-mono text-data tabular-nums text-ink-secondary">
                    {m.risk_score.toFixed(2)}
                  </td>
                  <td className="px-5 py-2.5">
                    <div className="flex gap-1.5">
                      <button
                        onClick={() => onToggleList(m.merchant_id, "allowed_merchants")}
                        disabled={disabled || !policy}
                        className={cn(
                          "rounded-control border px-2 py-1 text-label",
                          allowed
                            ? "border-allow-line bg-allow-tint text-allow"
                            : "border-line text-ink-muted hover:border-line-strong",
                        )}
                      >
                        Allow
                      </button>
                      <button
                        onClick={() => onToggleList(m.merchant_id, "blocked_merchants")}
                        disabled={disabled || !policy}
                        className={cn(
                          "rounded-control border px-2 py-1 text-label",
                          blocked
                            ? "border-block-line bg-block-tint text-block"
                            : "border-line text-ink-muted hover:border-line-strong",
                        )}
                      >
                        <ShieldOff size={10} className="mr-1 inline" /> Deny
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="border-t border-line p-4">
        {adding ? (
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1">
              <span className="label">Merchant ID</span>
              <input
                value={newId}
                onChange={(e) => setNewId(e.target.value)}
                placeholder="merch_example"
                className="rounded-control border border-line-strong bg-surface px-2.5 py-1.5 font-mono text-data text-ink"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="label">Category</span>
              <input
                value={newCategory}
                onChange={(e) => setNewCategory(e.target.value)}
                className="rounded-control border border-line-strong bg-surface px-2.5 py-1.5 text-caption text-ink"
              />
            </label>
            <Button size="sm" variant="primary" onClick={register} disabled={busy}>
              Register merchant
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setAdding(false)}>
              Cancel
            </Button>
          </div>
        ) : (
          <Button size="sm" variant="secondary" onClick={() => setAdding(true)}>
            <Plus size={14} /> Register a new merchant
          </Button>
        )}
        <p className="mt-2 text-label text-ink-muted">
          New merchants register unverified with a neutral risk score — that matches
          MerchantIn&apos;s real defaults, not an invented starting state.
        </p>
      </div>
    </>
  );
}
