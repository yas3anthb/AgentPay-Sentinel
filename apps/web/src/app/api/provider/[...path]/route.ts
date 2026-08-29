import { NextRequest, NextResponse } from "next/server";

import { PROVIDER_ORIGIN } from "@/lib/config";

export const dynamic = "force-dynamic";

type Ctx = { params: { path: string[] } };

/**
 * Read-only proxy to the mock payment provider — GET only, on purpose.
 *
 * This exists solely so the Configuration tab can show provider health and
 * its configured demo behaviour (success/decline/error/timeout). There is no
 * write path here and there must never be one: entering live payment
 * credentials into a browser form is not an appropriate flow under any
 * circumstance, mock or real. A real provider integration belongs behind a
 * backend-only secrets flow, never this proxy.
 */
export async function GET(request: NextRequest, { params }: Ctx) {
  const target = `${PROVIDER_ORIGIN}/${params.path.join("/")}${request.nextUrl.search}`;
  try {
    const upstream = await fetch(target, { cache: "no-store", signal: AbortSignal.timeout(5000) });
    const body = await upstream.text();
    return new NextResponse(body, {
      status: upstream.status,
      headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
    });
  } catch (error) {
    return NextResponse.json(
      { error: "PROVIDER_UNREACHABLE", message: `${PROVIDER_ORIGIN} did not answer: ${(error as Error).message}` },
      { status: 502 },
    );
  }
}
