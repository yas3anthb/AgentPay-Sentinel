import * as React from "react";

import { cn } from "@/lib/utils";

/** Every panel in the product. One radius, one border, one shadow. */
export function Panel({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <section className={cn("card", className)} {...props} />;
}

export function PanelHeader({
  title,
  subtitle,
  actions,
  className,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <header
      className={cn(
        "flex items-start justify-between gap-4 border-b border-line px-5 py-4",
        className,
      )}
    >
      <div className="min-w-0">
        <h2 className="text-section text-ink">{title}</h2>
        {subtitle ? (
          <p className="mt-1 max-w-prose text-caption text-ink-secondary">{subtitle}</p>
        ) : null}
      </div>
      {actions ? <div className="shrink-0">{actions}</div> : null}
    </header>
  );
}

/**
 * A labelled value. `mono` is opt-in and reserved for hashes, ids and policy
 * versions — the places fixed-width actually helps.
 */
export function Field({
  label,
  value,
  mono = false,
  className,
  title,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
  className?: string;
  title?: string;
}) {
  return (
    <div className={cn("min-w-0", className)}>
      <div className="label">{label}</div>
      <div
        title={title}
        className={cn(
          "mt-1 truncate text-ink",
          mono ? "font-mono text-data" : "text-body",
        )}
      >
        {value}
      </div>
    </div>
  );
}

/** Section heading used inside panel bodies, above a group of fields. */
export function Subhead({ children }: { children: React.ReactNode }) {
  return <h3 className="label mb-2">{children}</h3>;
}
