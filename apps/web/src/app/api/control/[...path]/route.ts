import { NextRequest } from "next/server";

import { CONTROL_PLANE_ORIGIN } from "@/lib/config";
import { proxy } from "@/lib/proxy";

export const dynamic = "force-dynamic";

type Ctx = { params: { path: string[] } };

// The admin key lives only in the server's environment. The browser calls this
// same-origin route; the route attaches the key and forwards to the control
// plane. A page bundle never contains the secret.
const ADMIN_KEY = process.env.ADMIN_API_KEY ?? "dev-admin-key";

const handler = (request: NextRequest, { params }: Ctx) =>
  proxy(request, params.path, CONTROL_PLANE_ORIGIN, {
    "x-admin-key": ADMIN_KEY,
    "x-admin-id": "web-console",
  });

export {
  handler as GET,
  handler as POST,
  handler as PUT,
  handler as PATCH,
  handler as DELETE,
};
