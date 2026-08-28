import { NextRequest } from "next/server";

import { SIMULATOR_ORIGIN } from "@/lib/config";
import { proxy } from "@/lib/proxy";

export const dynamic = "force-dynamic";

type Ctx = { params: { path: string[] } };

const handler = (request: NextRequest, { params }: Ctx) =>
  proxy(request, params.path, SIMULATOR_ORIGIN);

export {
  handler as GET,
  handler as POST,
  handler as PUT,
  handler as PATCH,
  handler as DELETE,
};
