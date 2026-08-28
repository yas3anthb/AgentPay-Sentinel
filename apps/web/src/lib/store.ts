"use client";

import { create } from "zustand";

import type { DecisionResponse } from "@/lib/api/gateway";
import type { RunSummary, SimulatorError } from "@/lib/api/transcript";
import type { StageEvent } from "@/lib/pipeline";

export type Scenario = "clean" | "adversarial" | "approval" | "raw";

export interface ScenarioDef {
  id: Scenario;
  label: string;
  description: string;
  /** null for the raw path, which bypasses the agent entirely. */
  path: string | null;
}

export const SCENARIOS: ScenarioDef[] = [
  {
    id: "clean",
    label: "Clean purchase",
    description: "The crew researches, builds a cart, the reviewer signs off, Sentinel allows it.",
    path: "/simulate/clean-purchase",
  },
  {
    id: "adversarial",
    label: "Adversarial (injected merchant content)",
    description:
      "The top search result is a poisoned product page. The injection reaches the agent verbatim; Sentinel is what stops it.",
    path: "/simulate/adversarial",
  },
  {
    id: "approval",
    label: "Approval-required",
    description:
      "Over the delegated approval threshold. The graph pauses on an interrupt — it does not poll.",
    path: "/simulate/approval-flow",
  },
  {
    id: "raw",
    label: "Raw payment intent (bypass the agent)",
    description:
      "Posts straight to the gateway with no agent in the loop, for probing the policy engine on its own.",
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
