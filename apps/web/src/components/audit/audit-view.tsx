"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, ChevronLeft, ChevronRight, ShieldAlert } from "lucide-react";

import { RegoBlock } from "@/lib/rego-highlight";
import { Badge, DecisionPill } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Panel, PanelHeader } from "@/components/ui/panel";
import { GATEWAY_URL } from "@/lib/config";
import { cn, shortHash } from "@/lib/utils";

interface AuditEvent {
  seq: number;
  event_id: string;
  event_type: string;
  created_at: string;
  payment_authorization_id: string | null;
  decision: string | null;
  reason_codes: string[];
  policy_version: string | null;
  prev_hash: string;
  event_hash: string;
}

interface ChainVerification {
  valid: boolean;
  events_checked: number;
  head_hash?: string;
  broken_at_seq?: number;
  broken_event_id?: string;
  expected_hash?: string;
  stored_hash?: string;
  claim: string;
}

const PAGE_SIZE = 25;

export function AuditView({ policies }: { policies: { name: string; source: string }[] }) {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [page, setPage] = useState(0);
  const [verification, setVerification] = useState<ChainVerification | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [selected, setSelected] = useState(policies[0]?.name ?? "");
  const [policyVersion, setPolicyVersion] = useState<string>("");

  const load = useCallback(async () => {
    const response = await fetch(`${GATEWAY_URL}/v1/audit/events?limit=200`, {
      cache: "no-store",
    });
    if (!response.ok) return;
    const body = (await response.json()) as { events?: AuditEvent[] };
    setEvents(body.events ?? []);
    setPolicyVersion(body.events?.[0]?.policy_version ?? "");
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 5000);
    return () => clearInterval(id);
  }, [load]);

  const verify = async () => {
    setVerifying(true);
    try {
      const response = await fetch(`${GATEWAY_URL}/v1/audit/verify`, { cache: "no-store" });
      setVerification((await response.json()) as ChainVerification);
    } finally {
      setVerifying(false);
    }
  };

  const pageEvents = events.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const pages = Math.max(1, Math.ceil(events.length / PAGE_SIZE));
  const policy = policies.find((p) => p.name === selected);

  return (
    <div className="flex flex-col gap-5">
      <Panel>
        <PanelHeader
          title="Audit chain"
          subtitle="Every decision is recorded — approvals and allows, not just blocks."
          actions={
            <Button onClick={verify} disabled={verifying} variant="secondary" size="sm">
              {verifying ? "Recomputing…" : "Verify chain"}
            </Button>
          }
        />
        {verification ? <Verification result={verification} /> : null}
      </Panel>

      <Panel>
        <PanelHeader
          title="Events"
          subtitle={`${events.length} recorded · page ${page + 1} of ${pages}`}
          actions={
            <div className="flex gap-1">
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
              >
                <ChevronLeft size={14} /> Prev
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setPage((p) => Math.min(pages - 1, p + 1))}
                disabled={page >= pages - 1}
              >
                Next <ChevronRight size={14} />
              </Button>
            </div>
          }
        />
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left">
            <thead>
              <tr className="border-b border-line">
                {["Seq", "Time", "Type", "Decision", "Reasons", "Hash", "Chains to"].map((h) => (
                  <th key={h} className="label whitespace-nowrap px-4 py-2.5 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pageEvents.map((event) => (
                <tr key={event.event_id} className="border-b border-line">
                  <td className="px-4 py-2.5 font-mono text-data tabular-nums text-ink-muted">
                    {event.seq}
                  </td>
                  <td className="whitespace-nowrap px-4 py-2.5 font-mono text-data text-ink-muted">
                    {new Date(event.created_at).toLocaleTimeString()}
                  </td>
                  <td className="px-4 py-2.5 text-caption text-ink-secondary">
                    {event.event_type}
                  </td>
                  <td className="px-4 py-2.5">
                    {event.decision ? (
                      <DecisionPill decision={event.decision} />
                    ) : (
                      <span className="text-ink-muted">—</span>
                    )}
                  </td>
                  <td className="max-w-[260px] px-4 py-2.5">
                    <span className="line-clamp-1 font-mono text-label normal-case tracking-normal text-ink-muted">
                      {event.reason_codes.join(" · ") || "—"}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 font-mono text-data text-ink">
                    {shortHash(event.event_hash, 14)}
                  </td>
                  <td className="px-4 py-2.5 font-mono text-data text-ink-muted">
                    {shortHash(event.prev_hash, 14)}
                  </td>
                </tr>
              ))}
              {pageEvents.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-caption text-ink-muted">
                    No events yet
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel>
        <PanelHeader
          title="Policy"
          subtitle="Read-only. The decision surface, exactly as the policy engine loads it."
          actions={policyVersion ? <Badge tone="accent">Active {policyVersion}</Badge> : null}
        />
        <div className="flex flex-wrap gap-1 border-b border-line px-3 py-2">
          {policies.map((file) => (
            <button
              key={file.name}
              onClick={() => setSelected(file.name)}
              className={cn(
                "rounded-control px-2.5 py-1.5 font-mono text-data transition-colors",
                file.name === selected
                  ? "bg-accent-tint text-accent"
                  : "text-ink-muted hover:bg-surface-sunken hover:text-ink-secondary",
              )}
            >
              {file.name}
            </button>
          ))}
        </div>
        {policy ? (
          <div className="max-h-[560px] overflow-auto bg-surface-sunken">
            <RegoBlock source={policy.source} />
          </div>
        ) : (
          <p className="p-5 text-caption text-ink-muted">
            No .rego files found. Set POLICIES_DIR if the policies live outside ../../policies.
          </p>
        )}
      </Panel>
    </div>
  );
}

/** Shows what was checked, not just a green tick. */
function Verification({ result }: { result: ChainVerification }) {
  const Icon = result.valid ? CheckCircle2 : ShieldAlert;
  return (
    <div
      className={cn(
        "border-b border-line p-5",
        result.valid ? "bg-allow-tint/50" : "bg-block-tint/60",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Icon size={16} className={result.valid ? "text-allow" : "text-block"} />
        <Badge tone={result.valid ? "allow" : "block"}>
          {result.valid ? "Chain intact" : "Chain broken"}
        </Badge>
        <span className="text-caption text-ink-secondary">
          {result.events_checked} links recomputed from the genesis hash
        </span>
      </div>

      {result.valid ? (
        <div className="mt-3.5 grid gap-4 sm:grid-cols-2">
          <Field label="Head hash" value={shortHash(result.head_hash, 32)} mono />
          <Field label="Claim" value={result.claim} />
        </div>
      ) : (
        <div className="mt-3.5 grid gap-4 sm:grid-cols-2">
          <Field label="First broken link" value={`Seq ${result.broken_at_seq}`} />
          <Field label="Event" value={result.broken_event_id ?? "—"} mono />
          <Field label="Expected" value={shortHash(result.expected_hash, 26)} mono />
          <Field label="Stored" value={shortHash(result.stored_hash, 26)} mono />
        </div>
      )}

      <p className="mt-3.5 text-caption text-ink-secondary">
        Each event is re-hashed with its predecessor and compared to what is stored.
        Tamper-evident within the current trust boundary — anyone with full database write
        access could rebuild the chain, so the claim stops there.
      </p>
    </div>
  );
}
