import { readdir, readFile } from "node:fs/promises";
import path from "node:path";

import { AuditView } from "@/components/audit/audit-view";

export const metadata = { title: "Audit & Policy · AgentPay Sentinel" };
export const dynamic = "force-dynamic";

export interface PolicyFile {
  name: string;
  source: string;
}

/**
 * Policies are read from disk on the server. They are never fetched from the
 * gateway and never editable here — this is a viewer.
 */
async function loadPolicies(): Promise<PolicyFile[]> {
  const dir = process.env.POLICIES_DIR ?? path.resolve(process.cwd(), "../../policies");
  try {
    const names = (await readdir(dir))
      .filter((n) => n.endsWith(".rego") && !n.endsWith("_test.rego"))
      .sort();
    return await Promise.all(
      names.map(async (name) => ({
        name,
        source: await readFile(path.join(dir, name), "utf8"),
      })),
    );
  } catch {
    return [];
  }
}

export default async function AuditPage() {
  return <AuditView policies={await loadPolicies()} />;
}
