import Link from "next/link";

import { AmbientBackground } from "@/components/effects/ambient-background";
import { HealthStrip } from "@/components/status/health-strip";
import { IdlePipelinePreview } from "@/components/pipeline/idle-preview";
import { Button } from "@/components/ui/button";
import { Panel, PanelHeader } from "@/components/ui/panel";

export default function OverviewPage() {
  return (
    <div className="flex flex-col gap-8">
      {/* Confined to the hero only — the health strip and claim cards below
          need a flat, unobstructed background to stay legible, and letting
          the effect bleed the full page height is what made it read as
          clutter rather than texture in an earlier pass. */}
      <section className="relative overflow-hidden rounded-panel">
        <AmbientBackground />
        <div className="relative grid gap-8 p-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.9fr)]">
        <div className="flex flex-col justify-center gap-5 py-4">
          <p className="label text-accent">Pre-payment security gateway</p>
          <h1 className="text-balance text-display text-ink">
            An AI agent can ask to spend your money.{" "}
            <span className="text-accent">Sentinel decides whether it can.</span>
          </h1>
          <p className="max-w-xl text-body text-ink-secondary">
            This is not a fraud dashboard reviewing charges after the fact. Sentinel sits
            between an autonomous shopping agent and the payment provider and refuses by
            default — a request has to pass identity, content analysis, policy evaluation and
            authorization before any payment token is created. When it refuses, the provider is
            never contacted at all.
          </p>
          <div className="flex flex-wrap items-center gap-2.5">
            <Button asChild variant="primary" size="lg">
              <Link href="/test">Open Test Console</Link>
            </Button>
            <Button asChild variant="secondary" size="lg">
              <Link href="/audit">Inspect the audit chain</Link>
            </Button>
          </div>
        </div>

        <Link
          href="/test"
          className="group relative block overflow-hidden rounded-panel border border-line bg-surface shadow-card transition-shadow hover:shadow-raised"
          aria-label="Open the Test Console"
        >
          <IdlePipelinePreview />
          <span className="pointer-events-none absolute bottom-4 left-5 text-caption font-medium text-ink-secondary transition-colors group-hover:text-accent">
            Seven checks, every payment · Click to try one →
          </span>
        </Link>
        </div>
      </section>

      <HealthStrip />

      <div className="grid gap-5 md:grid-cols-3">
        <Claim
          title="One decision-maker"
          body="Risk scoring never issues a verdict on its own — only the policy engine returns Allow, Approval required, or Blocked. Two systems that could both say “blocked” would eventually disagree."
        />
        <Claim
          title="Denies by default"
          body="An unreachable policy engine, a timed-out classifier, an unreadable revocation list, an unhandled error — every one of these resolves to Blocked. Silence is never treated as approval."
        />
        <Claim
          title="Tamper-evident record"
          body="Every decision is written to a hash-chained ledger, approvals included. The chain proves nothing was altered after the fact, within the boundary of who can write to the database."
        />
      </div>
    </div>
  );
}

function Claim({ title, body }: { title: string; body: string }) {
  return (
    <Panel>
      <PanelHeader title={title} />
      <p className="px-5 py-4 text-caption text-ink-secondary">{body}</p>
    </Panel>
  );
}
