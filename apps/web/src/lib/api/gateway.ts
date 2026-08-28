import createClient from "openapi-fetch";

import { GATEWAY_URL } from "@/lib/config";

import type { components, paths } from "./schema/gateway";

/**
 * Typed client for the Sentinel gateway.
 *
 * `paths` is generated from the gateway's live /openapi.json by
 * `npm run gen:api` — no response shape in this app is hand-written.
 */
export const gateway = createClient<paths>({ baseUrl: GATEWAY_URL });

export type DecisionResponse = components["schemas"]["DecisionResponse"];
export type RiskAssessment = components["schemas"]["RiskAssessment"];
export type RiskSignals = components["schemas"]["RiskSignals"];
export type Decision = components["schemas"]["Decision"];
export type PaymentState = components["schemas"]["PaymentState"];
export type PaymentIntent = components["schemas"]["PaymentIntent"];
export type AuthorizationToken = components["schemas"]["AuthorizationToken"];
