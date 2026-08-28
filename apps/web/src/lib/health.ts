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
    classifierMode: classifierMode(Boolean(gatewayReady)),
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

function classifierMode(reachable: boolean): StackHealth["classifierMode"] {
  /*
   * The gateway does not expose its classifier mode on /readyz, and guessing
   * would be worse than saying so: a confident "fail-closed" badge on a stack
   * running with ALLOW_DEGRADED_CLASSIFIER=true is exactly the kind of
   * comfortable lie this UI is supposed to avoid.
   *
   * The real value is observable per transaction — every decision response
   * carries risk.signals.classifier_degraded — so the Test Console reports it
   * from actual run data, and this strip says only what it knows.
   */
  return reachable
    ? {
        label: "Reported per transaction",
        state: "unknown",
        detail:
          "The gateway does not publish classifier mode on /readyz. Run a transaction — every decision reports classifier_degraded.",
      }
    : { label: "Unknown", state: "unknown", detail: "gateway unreachable" };
}
