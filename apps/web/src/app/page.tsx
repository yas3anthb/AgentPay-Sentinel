import Link from "next/link";

import { HealthStrip } from "@/components/status/health-strip";
import { IdlePipelinePreview } from "@/components/pipeline/idle-preview";
import { Button } from "@/components/ui/button";
import { Panel, PanelHeader } from "@/components/ui/panel";

export default function OverviewPage() {
  return (
    <div className="flex flex-col gap-6">
      <section className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.9fr)]">
        <div className="flex flex-col justify-center gap-5 py-4">
          <p className="label-xs">Pre-payment security gateway</p>
          <h1 className="text-balance text-3xl font-medium leading-tight text-chalk sm:text-4xl">
            An AI agent can ask to spend your money.{" "}
            <span className="text-signal-idle">Sentinel decides whether it can.</span>
          </h1>
          <p className="max-w-xl text-sm leading-relaxed text-chalk-muted">
            This is not a fraud dashboard. Nothing here reviews charges after they happen.
            Sentinel sits between an autonomous shopping agent and the payment provider and
            refuses by default: a typed intent has to survive identity, content analysis,
            policy evaluation and authorization before a single-use token is ever minted.
            When it refuses, the provider is never contacted at all.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <Button asChild size="lg">
              <Link href="/test">Open Test Console</Link>
            </Button>
            <Button asChild variant="outline" size="lg">
              <Link href="/audit">Inspect the audit chain</Link>
            </Button>
          </div>
        </div>

        <Link
          href="/test"
          className="group relative block overflow-hidden rounded-lg border border-hairline bg-ink-raised/60"
          aria-label="Open the Test Console"
        >
          <IdlePipelinePreview />
          <span className="pointer-events-none absolute bottom-3 left-4 font-mono text-[10px] uppercase tracking-[0.16em] text-chalk-faint transition-colors group-hover:text-signal-idle">
            seven stages · click to run one →
          </span>
        </Link>
      </section>

      <HealthStrip />

      <div className="grid gap-4 md:grid-cols-3">
        <Claim
          title="One decider"
          body="The risk engine emits signals and never a verdict — there is a test that fails if the word BLOCK appears in it. OPA is the only component that returns ALLOW, REQUIRE_APPROVAL or BLOCK."
        />
        <Claim
          title="Deny by default"
          body="No policy bound, OPA unreachable, classifier timed out, revocation set unreadable, unhandled exception — every one resolves to BLOCK. Absence of a decision is never a yes."
        />
        <Claim
          title="Tamper-evident, not tamper-proof"
          body="Every decision is hash-chained, allows included. Anyone with full database write access could rebuild the chain, so the claim stops there until the head is anchored externally."
        />
      </div>
    </div>
  );
}

function Claim({ title, body }: { title: string; body: string }) {
  return (
    <Panel>
      <PanelHeader title={title} />
      <p className="px-4 py-3 text-[13px] leading-relaxed text-chalk-muted">{body}</p>
    </Panel>
  );
}
