import createClient from "openapi-fetch";

import { SIMULATOR_URL } from "@/lib/config";

import type { paths } from "./schema/simulator";

/**
 * Typed client for the agent simulator.
 *
 * A caveat worth knowing: the simulator's `/simulate/*` handlers are annotated
 * `-> dict`, so its OpenAPI schema declares those responses as a bare object
 * and there is nothing richer for openapi-typescript to emit. Request bodies
 * and paths ARE fully typed from the schema; the response *body* shape is
 * described in `transcript.ts` and validated at runtime instead, because
 * `apps/agent-simulator/` is out of scope for this change.
 */
export const simulator = createClient<paths>({ baseUrl: SIMULATOR_URL });

export type SimulationRequest =
  paths["/simulate/clean-purchase"]["post"]["requestBody"]["content"]["application/json"];
