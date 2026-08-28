"use client";

import { useCallback, useEffect, useState } from "react";

import { RegoBlock } from "@/lib/rego-highlight";
import { Badge, decisionTone } from "@/components/ui/badge";
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
    <div className="flex flex-col gap-4">
      <Panel>
        <PanelHeader
          title="Audit chain"
          subtitle="Every decision is recorded — allows and approvals, not just blocks."
          actions={
            <Button onClick={verify} disabled={verifying} variant="outline" size="sm">
              {verifying ? "recomputing…" : "Verify chain"}
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
                ← prev
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setPage((p) => Math.min(pages - 1, p + 1))}
                disabled={page >= pages - 1}
              >
                next →
              </Button>
            </div>
          }
        />
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left">
            <thead>
              <tr className="border-b border-hairline">
                {["seq", "time", "type", "decision", "reasons", "hash", "chains to"].map((h) => (
                  <th key={h} className="label-xs whitespace-nowrap px-3 py-2 font-normal">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pageEvents.map((event) => (
                <tr key={event.event_id} className="border-b border-hairline/60">
                  <td className="px-3 py-2 font-mono text-[10px] tabular-nums text-chalk-faint">
                    {event.seq}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 font-mono text-[10px] text-chalk-faint">
                    {new Date(event.created_at).toLocaleTimeString()}
                  </td>
                  <td className="px-3 py-2 font-mono text-[10px] text-chalk-muted">
                    {event.event_type}
                  </td>
                  <td className="px-3 py-2">
                    {event.decision ? (
                      <Badge tone={decisionTone(event.decision)}>{event.decision}</Badge>
                    ) : (
                      <span className="text-chalk-faint">—</span>
                    )}
                  </td>
                  <td className="max-w-[260px] px-3 py-2">
                    <span className="line-clamp-1 font-mono text-[9px] text-chalk-faint">
                      {event.reason_codes.join(" · ") || "—"}
                    </span>
                  </td>
                  <td className="px-3 py-2 font-mono text-[10px] text-chalk">
                    {shortHash(event.event_hash, 14)}
                  </td>
                  <td className="px-3 py-2 font-mono text-[10px] text-chalk-faint">
                    {shortHash(event.prev_hash, 14)}
                  </td>
                </tr>
              ))}
              {pageEvents.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-3 py-6 text-center text-[11px] text-chalk-faint">
                    no events yet
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
          subtitle="Read-only. The decision surface, exactly as OPA loads it."
          actions={
            policyVersion ? <Badge tone="idle">active {policyVersion}</Badge> : null
          }
        />
        <div className="flex flex-wrap gap-1 border-b border-hairline px-3 py-2">
          {policies.map((file) => (
            <button
              key={file.name}
              onClick={() => setSelected(file.name)}
              className={cn(
                "rounded px-2.5 py-1 font-mono text-[10px] transition-colors",
                file.name === selected
                  ? "bg-signal-idle/10 text-signal-idle"
                  : "text-chalk-faint hover:bg-hairline/60 hover:text-chalk-muted",
              )}
            >
              {file.name}
            </button>
          ))}
        </div>
        {policy ? (
          <div className="max-h-[560px] overflow-auto bg-ink/50">
            <RegoBlock source={policy.source} />
          </div>
        ) : (
          <p className="p-4 text-[11px] text-chalk-faint">
            No .rego files found. Set POLICIES_DIR if the policies live outside ../../policies.
          </p>
        )}
      </Panel>
    </div>
  );
}

/** Shows what was checked, not just a green tick. */
function Verification({ result }: { result: ChainVerification }) {
  return (
    <div
      className={cn(
        "border-b border-hairline p-4",
        result.valid ? "bg-signal-allow/[0.06]" : "bg-signal-block/[0.08]",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={result.valid ? "allow" : "block"}>
          {result.valid ? "chain intact" : "chain broken"}
        </Badge>
        <span className="font-mono text-[11px] text-chalk">
          {result.events_checked} links recomputed from the genesis hash
        </span>
      </div>

      {result.valid ? (
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <Field label="head hash" value={shortHash(result.head_hash, 32)} />
          <Field label="claim" value={result.claim} mono={false} />
        </div>
      ) : (
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <Field label="first broken link" value={`seq ${result.broken_at_seq}`} />
          <Field label="event" value={result.broken_event_id ?? "—"} />
          <Field label="expected" value={shortHash(result.expected_hash, 26)} />
          <Field label="stored" value={shortHash(result.stored_hash, 26)} />
        </div>
      )}

      <p className="mt-3 text-[11px] leading-relaxed text-chalk-muted">
        Each event is re-hashed with its predecessor and compared to what is stored. Tamper-
        evident within the current trust boundary — anyone with full database write access
        could rebuild the chain, so the claim stops there.
      </p>
    </div>
  );
}
