"use client";

import { gateway, type DecisionResponse } from "@/lib/api/gateway";
import { simulator } from "@/lib/api/simulator";
import { isSimulatorError, parseRun, type RunSummary, type SimulatorError } from "@/lib/api/transcript";
import { CONTROL_URL, SIMULATOR_URL } from "@/lib/config";

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

/** Mints a short-lived delegation token via the control plane (a separate,
 * authenticated service — the /api/control proxy attaches the admin key). */
async function mintToken(): Promise<string> {
  const response = await fetch(`${CONTROL_URL}/v1/admin/tokens`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      agent_id: "agent_shopper_01",
      user_id: "user_ada",
      delegation_id: "del_office_supplies",
      scopes: ["payments:authorize"],
      ttl_seconds: 3600,
    }),
  });
  if (!response.ok) throw new Error("could not mint a delegation token");
  const token = (await response.json())?.token;
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
  body: { instruction: string; budget: string; correlationId?: string | null },
): Promise<RunSummary> {
  const { correlationId, ...rest } = body;
  const response = await fetch(`${SIMULATOR_URL}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    // The simulator threads this to the gateway as X-Request-Id, so the live
    // pipeline view can follow this exact run instead of the firehose.
    body: JSON.stringify(correlationId ? { ...rest, correlation_id: correlationId } : rest),
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
