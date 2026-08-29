import { GATEWAY_URL, RELAY_HTTP_URL, SIMULATOR_URL } from "@/lib/config";

export type HealthState = "ok" | "degraded" | "down" | "unknown";

export interface ServiceHealth {
  name: string;
  state: HealthState;
  /** Shown verbatim. Never a tooltip — a degraded mode has to be visible. */
  detail: string;
}

export interface StackHealth {
  services: ServiceHealth[];
  classifierMode: { label: string; state: HealthState; detail: string };
  agentLlmMode: { label: string; state: HealthState; detail: string };
  policyVersion: string;
  checkedAt: string;
}

async function getJson(url: string, timeoutMs = 4000): Promise<unknown | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { signal: controller.signal, cache: "no-store" });
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

function rec(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}

export async function fetchStackHealth(): Promise<StackHealth> {
  const [gatewayReady, simulatorReady, relayReady] = await Promise.all([
    getJson(`${GATEWAY_URL}/readyz`),
    getJson(`${SIMULATOR_URL}/readyz`),
    getJson(`${RELAY_HTTP_URL}/readyz`),
  ]);

  const g = rec(gatewayReady);
  const gChecks = rec(g.checks);
  const s = rec(simulatorReady);
  const sChecks = rec(s.checks);
  const r = rec(relayReady);

  const services: ServiceHealth[] = [
    {
      name: "Gateway",
      state: gatewayReady ? (g.ready ? "ok" : "degraded") : "down",
      detail: gatewayReady ? `policy ${String(g.policy_version ?? "?")}` : "unreachable",
    },
    {
      name: "OPA (PDP)",
      state: gatewayReady ? (gChecks.opa === "ok" ? "ok" : "degraded") : "unknown",
      detail: gatewayReady ? String(gChecks.opa ?? "unknown") : "gateway unreachable",
    },
    {
      // The gateway's readiness reports its shared store, which is Redis in
      // Compose. Labelled as what it actually checks rather than implying a
      // separate probe we do not make.
      name: "Redis",
      state: gatewayReady ? (gChecks.store === "ok" ? "ok" : "degraded") : "unknown",
      detail: gatewayReady ? String(gChecks.store ?? "unknown") : "gateway unreachable",
    },
    {
      name: "Postgres",
      state: gatewayReady ? (g.ready ? "ok" : "degraded") : "unknown",
      detail: gatewayReady
        ? "reachable — the gateway answered a DB-backed readiness check"
        : "gateway unreachable",
    },
    {
      name: "Agent simulator",
      state: simulatorReady ? (s.ready ? "ok" : "degraded") : "down",
      detail: simulatorReady ? String(sChecks.gateway ?? "ready") : "unreachable",
    },
    {
      name: "Event relay",
      state: relayReady ? (r.ready ? "ok" : "degraded") : "down",
      detail: relayReady
        ? `${r.redis_connected ? "subscribed" : "redis disconnected"} · ${String(r.events_seen ?? 0)} events`
        : "unreachable",
    },
  ];

  const agentMode = String(s.llm_mode ?? "unknown");

  return {
    services,
    // Both modes are surfaced as first-class labelled states. A degraded
    // classifier or scripted agent reasoning is exactly what a viewer needs to
    // know up front, so neither is hidden behind a tooltip.
    classifierMode: classifierMode(Boolean(gatewayReady), rec(g.classifier)),
    agentLlmMode: {
      label: agentMode === "offline" ? "Offline / scripted" : "Live",
      state: agentMode === "offline" ? "degraded" : simulatorReady ? "ok" : "unknown",
      detail:
        agentMode === "offline"
          ? "Agent reasoning is a deterministic script. Sentinel decisions are still live."
          : "CrewAI agents are running against a real model.",
    },
    policyVersion: String(g.policy_version ?? "unknown"),
    checkedAt: new Date().toISOString(),
  };
}

function classifierMode(
  reachable: boolean,
  classifier: Record<string, unknown>,
): StackHealth["classifierMode"] {
  /*
   * /readyz now reports the CONFIGURED classifier mode (not a live probe — a
   * healthcheck must not spend an OpenAI call). The per-transaction truth still
   * lives in each decision's risk.signals.classifier_degraded, because a "live"
   * config can still degrade on a single call that times out. So this strip
   * states the configuration and points at the per-run signal for the rest.
   */
  if (!reachable) return { label: "Unknown", state: "unknown", detail: "gateway unreachable" };

  const mode = String(classifier.llm_mode ?? "unknown");
  const failClosed = classifier.fail_closed !== false;
  const layers = Array.isArray(classifier.deterministic_layers)
    ? classifier.deterministic_layers.join(" + ")
    : "rules + similarity";

  if (mode === "live") {
    return {
      label: "Live",
      state: "ok",
      detail: `LLM + ${layers}; fail-closed. Per-transaction status in each decision.`,
    };
  }
  if (mode === "offline") {
    return {
      label: "Offline",
      state: "degraded",
      detail: `LLM layer skipped; ${layers} only.${failClosed ? " Fails closed." : " ALLOW_DEGRADED_CLASSIFIER is on."}`,
    };
  }
  if (mode === "unconfigured") {
    return {
      label: "No API key",
      state: failClosed ? "degraded" : "down",
      detail: `LLM layer unavailable; ${layers} only.${failClosed ? " Fails closed on every transaction." : " Degraded classifier is TOLERATED — not safe."}`,
    };
  }
  return {
    label: "Reported per transaction",
    state: "unknown",
    detail: "Run a transaction — every decision reports classifier_degraded.",
  };
}
