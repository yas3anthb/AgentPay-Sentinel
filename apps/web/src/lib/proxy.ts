import { NextRequest, NextResponse } from "next/server";

/**
 * Server-side proxy to a backend service.
 *
 * Implemented as a route handler rather than a next.config rewrite on purpose:
 * rewrites are resolved at build time and baked into the routes manifest, so a
 * container built without GATEWAY_ORIGIN set would proxy to its own localhost
 * forever. This reads the environment on every request, so the same image runs
 * locally and in Compose without a rebuild.
 */
export async function proxy(
  request: NextRequest,
  segments: string[],
  origin: string,
): Promise<NextResponse> {
  const search = request.nextUrl.search;
  const target = `${origin}/${segments.join("/")}${search}`;

  const headers = new Headers();
  for (const name of ["authorization", "content-type", "accept", "x-request-id"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  const method = request.method;
  const body =
    method === "GET" || method === "HEAD" ? undefined : await request.arrayBuffer();

  try {
    const upstream = await fetch(target, {
      method,
      headers,
      body,
      cache: "no-store",
      // A crew run can take a while in live mode; don't cut it short here.
      signal: AbortSignal.timeout(120_000),
    });

    const responseHeaders = new Headers();
    const contentType = upstream.headers.get("content-type");
    if (contentType) responseHeaders.set("content-type", contentType);

    return new NextResponse(await upstream.arrayBuffer(), {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch (error) {
    // Surfaced as an explicit upstream failure — never a fabricated success.
    return NextResponse.json(
      {
        error: "UPSTREAM_UNREACHABLE",
        message: `${origin} did not answer: ${(error as Error).message}`,
      },
      { status: 502 },
    );
  }
}
