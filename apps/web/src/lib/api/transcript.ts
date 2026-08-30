/**
 * Runtime shape of an agent-simulator run.
 *
 * These are NOT hand-written substitutes for a generated type. The simulator
 * declares `/simulate/*` responses as `dict` in its OpenAPI schema, so no
 * generator can produce anything more specific than `object`. Rather than
 * casting and hoping, the payload is parsed and narrowed here, and anything
 * unexpected degrades to a rendered-but-unknown step instead of throwing in a
 * React tree.
 */

export type StepKind =
  | "graph_transition"
  | "agent_step"
  | "tool_call"
  | "tool_result"
  | "gateway_decision"
  | "review"
  | "error"
  | "note";

export interface TranscriptStep {
  index: number;
  at: string;
  kind: StepKind | string;
  actor: string;
  name: string;
  summary: string;
  detail: Record<string, unknown>;
  latency_ms: number | null;
  /** True when the agent's reasoning was scripted rather than model-generated. */
  simulated: boolean;
}

export interface RunTranscript {
  run_id: string;
  scenario: string;
  mode: string;
  simulated: boolean;
  started_at: string;
  elapsed_ms: number;
  steps: TranscriptStep[];
}

export interface RunSummary {
  run_id: string;
  scenario: string;
  /** "live" or "offline-deterministic". */
  mode: string;
  simulated_reasoning: boolean;
  status: string;
  /** The X-Request-Id every gateway call in this run carried, for live-stream filtering. */
  request_id: string | null;
  decision: "ALLOW" | "REQUIRE_APPROVAL" | "BLOCK" | null;
  reason_codes: string[];
  approval_request_id: string | null;
  sentinel: {
    payment_authorization_id?: string | null;
    state?: string | null;
    policy_version?: string | null;
    risk?: {
      signals?: Record<string, unknown>;
      weighted_score?: number;
    } | null;
    audit_event_id?: string | null;
    audit_hash?: string | null;
    provider_reference?: string | null;
    message?: string | null;
  };
  provider_calls: { before: number | null; after: number | null; delta: number | null };
  transcript: RunTranscript;
  warning?: string;
  injection?: {
    payload_sha256: string;
    payload_chars: number;
    reached_agent_unmodified: boolean;
  };
}

/** The shape the simulator returns on a failed run: an error, never a transcript. */
export interface SimulatorError {
  error: string;
  message: string;
  detail?: Record<string, unknown>;
}

export function isSimulatorError(value: unknown): value is SimulatorError {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as SimulatorError).error === "string" &&
    typeof (value as SimulatorError).message === "string"
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : {};
}

function parseStep(raw: unknown, fallbackIndex: number): TranscriptStep {
  const r = asRecord(raw);
  return {
    index: typeof r.index === "number" ? r.index : fallbackIndex,
    at: typeof r.at === "string" ? r.at : "",
    kind: typeof r.kind === "string" ? r.kind : "note",
    actor: typeof r.actor === "string" ? r.actor : "unknown",
    name: typeof r.name === "string" ? r.name : "step",
    summary: typeof r.summary === "string" ? r.summary : "",
    detail: asRecord(r.detail),
    latency_ms: typeof r.latency_ms === "number" ? r.latency_ms : null,
    // Defaults to true: if we cannot tell whether a step was real, the honest
    // answer is to mark it scripted rather than to imply it was live.
    simulated: typeof r.simulated === "boolean" ? r.simulated : true,
  };
}

export function parseRun(raw: unknown): RunSummary {
  const r = asRecord(raw);
  const t = asRecord(r.transcript);
  const steps = Array.isArray(t.steps) ? t.steps.map(parseStep) : [];
  const provider = asRecord(r.provider_calls);
  const injection = r.injection ? asRecord(r.injection) : undefined;

  return {
    run_id: String(r.run_id ?? ""),
    scenario: String(r.scenario ?? ""),
    mode: String(r.mode ?? "unknown"),
    simulated_reasoning: r.simulated_reasoning === true,
    status: String(r.status ?? "unknown"),
    request_id: typeof r.request_id === "string" ? r.request_id : null,
    decision: (r.decision as RunSummary["decision"]) ?? null,
    reason_codes: Array.isArray(r.reason_codes) ? r.reason_codes.map(String) : [],
    approval_request_id:
      typeof r.approval_request_id === "string" ? r.approval_request_id : null,
    sentinel: asRecord(r.sentinel) as RunSummary["sentinel"],
    provider_calls: {
      before: typeof provider.before === "number" ? provider.before : null,
      after: typeof provider.after === "number" ? provider.after : null,
      delta: typeof provider.delta === "number" ? provider.delta : null,
    },
    transcript: {
      run_id: String(t.run_id ?? r.run_id ?? ""),
      scenario: String(t.scenario ?? ""),
      mode: String(t.mode ?? r.mode ?? "unknown"),
      simulated: t.simulated === true,
      started_at: String(t.started_at ?? ""),
      elapsed_ms: typeof t.elapsed_ms === "number" ? t.elapsed_ms : 0,
      steps,
    },
    warning: typeof r.warning === "string" ? r.warning : undefined,
    injection: injection
      ? {
          payload_sha256: String(injection.payload_sha256 ?? ""),
          payload_chars: Number(injection.payload_chars ?? 0),
          reached_agent_unmodified: injection.reached_agent_unmodified === true,
        }
      : undefined,
  };
}
