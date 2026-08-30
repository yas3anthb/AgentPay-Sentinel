"use client";

import { useEffect, useState } from "react";

import { PipelineWalkthrough } from "@/components/explainer/pipeline-walkthrough";
import { Panel, PanelHeader } from "@/components/ui/panel";
import type { Decision } from "@/lib/api/gateway";
import { loadExplainerRuns, type ExplainerRun } from "@/lib/explainer-data";

const EMPTY: Record<Decision, ExplainerRun> = {
  ALLOW: {
    decision: "ALLOW", reasonCodes: [], weightedScore: 0, policyVersion: "",
    merchant: "", amount: "0.00", currency: "INR", source: null,
  },
  REQUIRE_APPROVAL: {
    decision: "REQUIRE_APPROVAL", reasonCodes: [], weightedScore: 0, policyVersion: "",
    merchant: "", amount: "0.00", currency: "INR", source: null,
  },
  BLOCK: {
    decision: "BLOCK", reasonCodes: [], weightedScore: 0, policyVersion: "",
    merchant: "", amount: "0.00", currency: "INR", source: null,
  },
};

/**
 * A stage-by-stage walkthrough for a technically literate reviewer.
 *
 * Every stage's copy is imported from `@/lib/pipeline` — the exact same
 * `STAGES` array the Test Console's stage table reads from — so this page
 * cannot drift into vaguer marketing language over time; there is only one
 * place stage descriptions are written.
 */
export function HowItWorksView() {
  const [decision, setDecision] = useState<Decision>("BLOCK");
  const [runs, setRuns] = useState<Record<Decision, ExplainerRun>>(EMPTY);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let alive = true;
    void loadExplainerRuns().then((r) => {
      if (alive) {
        setRuns(r);
        setLoaded(true);
      }
    });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <div>
        <p className="label text-accent">For technical review</p>
        <h1 className="mt-1 text-title text-ink">How Sentinel decides</h1>
        <p className="mt-2 max-w-2xl text-body text-ink-secondary">
          A request moves through seven checks in a fixed order. Pick a branch, then step
          through manually or let it play — each stage names exactly what it checked, using the
          same descriptions the Test Console shows.
        </p>
      </div>

      <Panel>
        <PanelHeader
          title="Pipeline walkthrough"
          subtitle={loaded ? undefined : "Loading recent transaction data…"}
        />
        <div className="p-5">
          <PipelineWalkthrough decision={decision} onDecisionChange={setDecision} run={runs[decision]} />
        </div>
      </Panel>
    </div>
  );
}
