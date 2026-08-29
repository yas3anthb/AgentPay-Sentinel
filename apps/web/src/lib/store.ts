"use client";

import { create } from "zustand";

import type { DecisionResponse } from "@/lib/api/gateway";
import type { RunSummary, SimulatorError } from "@/lib/api/transcript";
import type { StageEvent } from "@/lib/pipeline";

export type Scenario = "clean" | "adversarial" | "approval" | "raw";

export interface ScenarioDef {
  id: Scenario;
  label: string;
  /** One plain-language sentence a non-technical reader understands at a glance. */
  description: string;
  /** The precise mechanism. Shown as secondary, smaller text — never the lead. */
  technical: string;
  /** null for the raw path, which bypasses the agent entirely. */
  path: string | null;
}

export const SCENARIOS: ScenarioDef[] = [
  {
    id: "clean",
    label: "Clean purchase",
    description: "Runs a normal purchase end to end and approves it.",
    technical: "The agent researches, builds a cart, a reviewer signs off, Sentinel allows it.",
    path: "/simulate/clean-purchase",
  },
  {
    id: "adversarial",
    label: "Adversarial content",
    description: "Simulates an attack hidden in a product page, and shows it being stopped.",
    technical:
      "The top search result is a poisoned page. The injection reaches the agent verbatim; Sentinel is what blocks it.",
    path: "/simulate/adversarial",
  },
  {
    id: "approval",
    label: "Needs approval",
    description: "A purchase large enough to require a human's sign-off before it proceeds.",
    technical: "Over the delegated approval threshold. The workflow pauses on an interrupt — it does not poll.",
    path: "/simulate/approval-flow",
  },
  {
    id: "raw",
    label: "Raw payment request",
    description: "Sends a payment request directly, with no agent involved.",
    technical: "Posts straight to the gateway, for probing the policy engine on its own.",
    path: null,
  },
];

export type RunPhase = "idle" | "running" | "paused" | "done" | "error";

interface ConsoleState {
  scenario: Scenario;
  phase: RunPhase;
  requestId: string | null;
  run: RunSummary | null;
  rawDecision: DecisionResponse | null;
  error: SimulatorError | null;
  events: StageEvent[];
  startedAt: number | null;

  setScenario: (scenario: Scenario) => void;
  beginRun: (requestId: string | null) => void;
  setEvents: (events: StageEvent[]) => void;
  finishRun: (run: RunSummary) => void;
  finishRaw: (decision: DecisionResponse) => void;
  failRun: (error: SimulatorError) => void;
  reset: () => void;
}

export const useConsole = create<ConsoleState>((set) => ({
  scenario: "clean",
  phase: "idle",
  requestId: null,
  run: null,
  rawDecision: null,
  error: null,
  events: [],
  startedAt: null,

  setScenario: (scenario) =>
    set({ scenario, phase: "idle", run: null, rawDecision: null, error: null, events: [] }),
  beginRun: (requestId) =>
    set({
      phase: "running",
      requestId,
      run: null,
      rawDecision: null,
      error: null,
      events: [],
      startedAt: Date.now(),
    }),
  setEvents: (events) => set({ events }),
  finishRun: (run) =>
    set({ run, phase: run.status === "awaiting_approval" ? "paused" : "done" }),
  finishRaw: (rawDecision) => set({ rawDecision, phase: "done" }),
  failRun: (error) => set({ error, phase: "error" }),
  reset: () =>
    set({ phase: "idle", run: null, rawDecision: null, error: null, events: [], requestId: null }),
}));
