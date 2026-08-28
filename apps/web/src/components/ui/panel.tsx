import * as React from "react";

import { cn } from "@/lib/utils";

export function Panel({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <section className={cn("panel", className)} {...props} />;
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
        "flex items-start justify-between gap-4 border-b border-hairline px-4 py-3",
        className,
      )}
    >
      <div className="min-w-0">
        <h2 className="font-mono text-xs uppercase tracking-[0.14em] text-chalk">{title}</h2>
        {subtitle ? (
          <p className="mt-1 text-xs leading-relaxed text-chalk-muted">{subtitle}</p>
        ) : null}
      </div>
      {actions ? <div className="shrink-0">{actions}</div> : null}
    </header>
  );
}

export function Field({
  label,
  value,
  mono = true,
  className,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("min-w-0", className)}>
      <div className="label-xs">{label}</div>
      <div className={cn("mt-1 truncate text-sm text-chalk", mono && "font-mono text-xs")}>
        {value}
      </div>
    </div>
  );
}
