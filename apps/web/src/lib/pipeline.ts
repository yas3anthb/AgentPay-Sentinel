/** The seven pipeline stages, and the live event stream that drives them. */

export type StageId =
  | "identity"
  | "canonical"
  | "analyzer"
  | "risk"
  | "pdp"
  | "authorization"
  | "audit";

export type StageStatus =
  | "idle"
  | "started"
  | "passed"
  | "blocked"
  | "paused"
  | "failed"
  | "skipped";

export interface StageDef {
  id: StageId;
  label: string;
  short: string;
  blurb: string;
}

/** Order matters: it is the order the gateway actually runs them in. */
export const STAGES: StageDef[] = [
  { id: "identity", label: "Identity", short: "IDN", blurb: "Delegation JWT, agent scope, revocation set" },
  { id: "canonical", label: "Canonical Builder", short: "CAN", blurb: "Typed intent; free text quarantined as untrusted" },
  { id: "analyzer", label: "Intent Analyzer", short: "ANL", blurb: "Regex rules + LLM classifier + source trust" },
  { id: "risk", label: "Risk Engine", short: "RSK", blurb: "Signals only — emits no decision" },
  { id: "pdp", label: "OPA (PDP)", short: "PDP", blurb: "The only component that decides" },
  { id: "authorization", label: "Payment Authorization", short: "PAY", blurb: "Scoped single-use token, state machine" },
  { id: "audit", label: "Audit Ledger", short: "AUD", blurb: "Hash-chained; records every decision" },
];

export const STAGE_INDEX: Record<StageId, number> = Object.fromEntries(
  STAGES.map((s, i) => [s.id, i]),
) as Record<StageId, number>;

/** One stage-transition event as published by the gateway. */
export interface StageEvent {
  seq: number;
  request_id: string;
  payment_authorization_id: string;
  stage: StageId;
  status: Exclude<StageStatus, "idle">;
  latency_ms: number | null;
  elapsed_ms: number;
  at: string;
  detail: Record<string, unknown>;
  replayed?: boolean;
}

export interface StageState {
  status: StageStatus;
  latencyMs: number | null;
  elapsedMs: number | null;
  detail: Record<string, unknown>;
}

export type PipelineState = Record<StageId, StageState>;

export function emptyPipeline(): PipelineState {
  return Object.fromEntries(
    STAGES.map((s) => [s.id, { status: "idle", latencyMs: null, elapsedMs: null, detail: {} }]),
  ) as PipelineState;
}

/**
 * Fold events into stage state.
 *
 * Publishes are fire-and-forget on the gateway side and can arrive out of
 * order, so events are applied in `seq` order — the sequence assigned at the
 * moment each stage boundary was actually crossed. Sorting by arrival would
 * show a plausible-looking but wrong ordering.
 */
export function reducePipeline(events: StageEvent[]): PipelineState {
  const state = emptyPipeline();
  for (const event of [...events].sort((a, b) => a.seq - b.seq)) {
    const stage = state[event.stage];
    if (!stage) continue;
    stage.status = event.status;
    stage.elapsedMs = event.elapsed_ms;
    if (event.latency_ms !== null) stage.latencyMs = event.latency_ms;
    stage.detail = { ...stage.detail, ...event.detail };
  }
  return state;
}

/**
 * The index where the beam stops, or null if it ran to the end.
 *
 * Note the audit stage is excluded from the break: a blocked transaction is
 * still recorded, so the ledger genuinely lights up after the break. Drawing
 * it dark would be a prettier animation and a false one.
 */
export function severedAt(state: PipelineState): number | null {
  for (const stage of STAGES) {
    const status = state[stage.id].status;
    if (status === "blocked" || status === "failed") return STAGE_INDEX[stage.id];
  }
  return null;
}

export function isSkipped(state: PipelineState, id: StageId): boolean {
  return state[id].status === "skipped";
}

export function statusColor(status: StageStatus): string {
  switch (status) {
    case "passed":
      return "#3FBF7F";
    case "blocked":
    case "failed":
      return "#F2637A";
    case "paused":
      return "#E0A340";
    case "started":
      return "#4EC9C0";
    case "skipped":
      return "#2A3644";
    default:
      return "#1F2A36";
  }
}
