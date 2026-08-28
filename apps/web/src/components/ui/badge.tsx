import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.1em]",
  {
    variants: {
      tone: {
        neutral: "border-hairline-bright bg-hairline/40 text-chalk-muted",
        idle: "border-signal-idle/40 bg-signal-idle/10 text-signal-idle",
        allow: "border-signal-allow/40 bg-signal-allow/10 text-signal-allow",
        approval: "border-signal-approval/40 bg-signal-approval/10 text-signal-approval",
        block: "border-signal-block/40 bg-signal-block/10 text-signal-block",
        /** Scripted agent reasoning. Never used for anything live. */
        simulated: "border-signal-simulated/50 bg-signal-simulated/10 text-signal-simulated",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export function Badge({
  className,
  tone,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}

/** Maps a gateway decision onto the app's four signal colours. */
export function decisionTone(
  decision: string | null | undefined,
): "allow" | "approval" | "block" | "neutral" {
  if (decision === "ALLOW") return "allow";
  if (decision === "REQUIRE_APPROVAL") return "approval";
  if (decision === "BLOCK") return "block";
  return "neutral";
}
