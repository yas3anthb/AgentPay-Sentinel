"use client";

import { gateway, type DecisionResponse } from "@/lib/api/gateway";
import { simulator } from "@/lib/api/simulator";
import { isSimulatorError, parseRun, type RunSummary, type SimulatorError } from "@/lib/api/transcript";
import { SIMULATOR_URL } from "@/lib/config";

export interface RawIntentForm {
  merchantId: string;
  amount: string;
  currency: string;
  sku: string;
  itemName: string;
  quantity: number;
  purpose: string;
  merchantContent: string;
  sourceType: "official_api" | "verified_catalog" | "scraped_page" | "email" | "unknown";
}

/** Mints a short-lived delegation token for the demo agent. */
async function mintToken(): Promise<string> {
  const { data, error } = await gateway.POST("/v1/admin/tokens", {
    body: {
      agent_id: "agent_shopper_01",
      user_id: "user_ada",
      delegation_id: "del_office_supplies",
      scopes: ["payments:authorize"],
      ttl_seconds: 3600,
    },
  });
  if (error || !data) throw new Error("could not mint a delegation token");
  // The gateway annotates this handler `-> dict`, so its generated type is an
  // empty record. Narrowed at runtime rather than asserted through.
  const token = (data as Record<string, unknown>).token;
  if (typeof token !== "string") throw new Error("token endpoint returned no token");
  return token;
}

/**
 * The raw path: straight to the gateway, no agent in the loop.
 *
 * The X-Request-Id is what makes the live pipeline view work — the caller
 * subscribes to it before posting, so the 3D scene follows this exact request.
 */
export async function runRawIntent(
  form: RawIntentForm,
  requestId: string,
): Promise<DecisionResponse> {
  const token = await mintToken();
  const total = (Number(form.amount) * form.quantity).toFixed(2);

  const { data, error, response } = await gateway.POST("/v1/payment-intents", {
    headers: { Authorization: `Bearer ${token}`, "X-Request-Id": requestId },
    body: {
      idempotency_key: `web-${crypto.randomUUID().slice(0, 18)}`,
      agent_id: "agent_shopper_01",
      user_id: "user_ada",
      delegation_id: "del_office_supplies",
      merchant_id: form.merchantId,
      merchant_verified: true,
      amount: total,
      currency: form.currency,
      items: [
        {
          sku: form.sku,
          name: form.itemName,
          quantity: form.quantity,
          unit_price: form.amount,
        },
      ],
      purpose: form.purpose,
      merchant_content: {
        source_type: form.sourceType,
        source_url: "https://console.example/manual",
        text: form.merchantContent,
      },
      tool_arguments: { origin: "test-console" },
    } as never,
  });

  if (data) return data as DecisionResponse;

  // A 4xx/5xx body is shown as-is. The console never invents a decision.
  throw new Error(
    `gateway returned ${response.status}: ${JSON.stringify(error ?? {}).slice(0, 400)}`,
  );
}

export async function runSimulation(
  path: string,
  body: { instruction: string; budget: string },
): Promise<RunSummary> {
  const response = await fetch(`${SIMULATOR_URL}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    // Requirement: on a 502 show the raw error code and message. Never
    // synthesize a transcript to fill the screen.
    if (isSimulatorError(payload)) throw payload;
    throw {
      error: `HTTP_${response.status}`,
      message: typeof payload === "string" ? payload : JSON.stringify(payload ?? {}).slice(0, 500),
    } satisfies SimulatorError;
  }
  return parseRun(payload);
}

export async function approveRun(runId: string): Promise<RunSummary> {
  const response = await fetch(`${SIMULATOR_URL}/simulate/${runId}/approve`, { method: "POST" });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    if (isSimulatorError(payload)) throw payload;
    throw { error: `HTTP_${response.status}`, message: "approval failed" } satisfies SimulatorError;
  }
  return parseRun(payload);
}

export async function resetDemoState(): Promise<void> {
  await simulator.POST("/simulate/reset", {});
}
