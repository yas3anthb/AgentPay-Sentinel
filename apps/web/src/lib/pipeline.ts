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
  /** Plain language, for the first read. Leads everywhere. */
  plain: string;
  /** The precise technical description. Available on demand, never dumped. */
  technical: string;
}

/** Order matters: it is the order the gateway actually runs them in. */
export const STAGES: StageDef[] = [
  {
    id: "identity",
    label: "Identity",
    short: "IDN",
    plain: "Confirms this agent is who it claims to be",
    technical: "Delegation JWT signature, agent scope, revocation set lookup",
  },
  {
    id: "canonical",
    label: "Request check",
    short: "CAN",
    plain: "Turns the request into a strict, typed payment record",
    technical: "Canonical transaction builder; free text quarantined as untrusted content",
  },
  {
    id: "analyzer",
    label: "Content analysis",
    short: "ANL",
    plain: "Scans the merchant's text for attempts to manipulate the agent",
    technical: "Regex rule layer + LLM injection classifier + source trust scoring",
  },
  {
    id: "risk",
    label: "Risk scoring",
    short: "RSK",
    plain: "Scores the transaction against spending limits and history",
    technical: "Risk engine — emits weighted signals only, never a decision",
  },
  {
    id: "pdp",
    label: "Policy decision",
    short: "PDP",
    plain: "Applies the written policy and decides",
    technical: "Open Policy Agent — the only component that returns a verdict",
  },
  {
    id: "authorization",
    label: "Payment authorization",
    short: "PAY",
    plain: "Issues a one-time token and charges the provider",
    technical: "Scoped single-use token issuance and the payment state machine",
  },
  {
    id: "audit",
    label: "Audit record",
    short: "AUD",
    plain: "Writes a tamper-evident record of the outcome",
    technical: "SHA-256 hash-chained ledger; records every decision, not just blocks",
  },
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

/** Hex values, for the canvas/SVG renderers. Mirrors the Tailwind tokens. */
export function statusColor(status: StageStatus): string {
  switch (status) {
    case "passed":
      return "#0F7A4E";
    case "blocked":
    case "failed":
      return "#C2334A";
    case "paused":
      return "#9A5B00";
    case "started":
      return "#4F46E5";
    case "skipped":
      return "#CBD5E1";
    default:
      return "#94A3B8";
  }
}

export type StageTone = "allow" | "approval" | "block" | "accent" | "inactive" | "neutral";

/** The one mapping from stage status to the product's pill tones. */
export function statusTone(status: StageStatus): StageTone {
  switch (status) {
    case "passed":
      return "allow";
    case "blocked":
    case "failed":
      return "block";
    case "paused":
      return "approval";
    case "started":
      return "accent";
    case "skipped":
      return "inactive";
    default:
      return "neutral";
  }
}

/** Result wording for the stages table. Plain, not jargon. */
export function statusLabel(status: StageStatus): string {
  switch (status) {
    case "passed":
      return "Passed";
    case "blocked":
      return "Blocked";
    case "failed":
      return "Failed";
    case "paused":
      return "Paused";
    case "started":
      return "Running";
    case "skipped":
      return "Not reached";
    default:
      return "Waiting";
  }
}
