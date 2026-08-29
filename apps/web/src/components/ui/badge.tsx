import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * One pill component for the whole product.
 *
 * `allow` / `approval` / `block` are verdicts and carry the only saturated
 * colours in the UI. Everything else is neutral, so a coloured pill anywhere
 * on screen means a decision was made.
 */
const badgeVariants = cva(
  "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-0.5 text-label",
  {
    variants: {
      tone: {
        neutral: "border-line-strong bg-surface-sunken text-ink-secondary",
        accent: "border-accent/25 bg-accent-tint text-accent",
        notice: "border-notice-line bg-notice-tint text-notice",
        allow: "border-allow-line bg-allow-tint text-allow",
        approval: "border-approval-line bg-approval-tint text-approval",
        block: "border-block-line bg-block-tint text-block",
        inactive: "border-inactive-line bg-inactive-tint text-inactive",
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

export type Tone = NonNullable<VariantProps<typeof badgeVariants>["tone"]>;

/** Maps a gateway decision onto its reserved colour. Used everywhere. */
export function decisionTone(decision: string | null | undefined): Tone {
  if (decision === "ALLOW") return "allow";
  if (decision === "REQUIRE_APPROVAL") return "approval";
  if (decision === "BLOCK") return "block";
  return "neutral";
}

const DECISION_LABEL: Record<string, string> = {
  ALLOW: "Allowed",
  REQUIRE_APPROVAL: "Approval required",
  BLOCK: "Blocked",
};

/** A verdict, in words a non-technical reader understands. */
export function DecisionPill({
  decision,
  className,
}: {
  decision: string | null | undefined;
  className?: string;
}) {
  if (!decision) return <Badge className={className}>No decision</Badge>;
  return (
    <Badge tone={decisionTone(decision)} className={className}>
      {DECISION_LABEL[decision] ?? decision}
    </Badge>
  );
}

/**
 * Scripted vs live.
 *
 * The distinction is textural rather than chromatic — a dashed outline versus
 * a solid one with a filled dot — because the saturated colours are spent on
 * verdicts. It still reads instantly side by side, and it costs no colour.
 */
export function OriginPill({ simulated, className }: { simulated: boolean; className?: string }) {
  return simulated ? (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-dashed border-ink-muted/70 bg-surface-sunken px-2 py-0.5 text-label text-ink-secondary",
        className,
      )}
      title="This step's reasoning was scripted, not produced by a language model."
    >
      Scripted
    </span>
  ) : (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-ink-secondary/40 bg-surface px-2 py-0.5 text-label text-ink",
        className,
      )}
      title="This step really happened against the live service."
    >
      <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-ink" />
      Live
    </span>
  );
}
