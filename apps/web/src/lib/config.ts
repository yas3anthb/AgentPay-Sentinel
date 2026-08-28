/**
 * Service endpoints.
 *
 * Browser code uses the same-origin proxy paths declared in next.config.mjs.
 * Server-side code (route handlers, server components) talks to the services
 * directly, since it is not subject to CORS and should not round-trip through
 * its own proxy.
 */
const isServer = typeof window === "undefined";

export const GATEWAY_ORIGIN = process.env.GATEWAY_ORIGIN ?? "http://localhost:8080";
export const SIMULATOR_ORIGIN = process.env.SIMULATOR_ORIGIN ?? "http://localhost:9200";

export const GATEWAY_URL = isServer ? GATEWAY_ORIGIN : "/api/gateway";
export const SIMULATOR_URL = isServer ? SIMULATOR_ORIGIN : "/api/simulator";

/** WebSockets bypass CORS, so the relay is reached directly. */
export const RELAY_WS_URL =
  process.env.NEXT_PUBLIC_RELAY_WS_URL ?? "ws://localhost:9300";
export const RELAY_HTTP_URL = RELAY_WS_URL.replace(/^ws/, "http");
