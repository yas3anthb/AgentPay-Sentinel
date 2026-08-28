"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { fetchStackHealth, type HealthState, type StackHealth } from "@/lib/health";
import { cn } from "@/lib/utils";

const DOT: Record<HealthState, string> = {
  ok: "bg-signal-allow",
  degraded: "bg-signal-approval",
  down: "bg-signal-block",
  unknown: "bg-chalk-faint",
};

export function HealthStrip({ intervalMs = 5000 }: { intervalMs?: number }) {
  const [health, setHealth] = useState<StackHealth | null>(null);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      const next = await fetchStackHealth();
      if (alive) setHealth(next);
    };
    void tick();
    const id = setInterval(tick, intervalMs);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [intervalMs]);

  if (!health) {
    return (
      <div className="panel px-4 py-3 font-mono text-xs text-chalk-faint">
        checking services…
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-t-lg bg-hairline sm:grid-cols-3 lg:grid-cols-6">
        {health.services.map((service) => (
          <div key={service.name} className="bg-ink-raised px-3.5 py-3">
            <div className="flex items-center gap-2">
              <span
                className={cn("h-1.5 w-1.5 shrink-0 rounded-full", DOT[service.state])}
                aria-hidden
              />
              <span className="truncate font-mono text-[11px] text-chalk">{service.name}</span>
            </div>
            <p className="mt-1.5 truncate text-[11px] text-chalk-faint" title={service.detail}>
              {service.detail}
            </p>
            <span className="sr-only">status: {service.state}</span>
          </div>
        ))}
      </div>

      {/* Mode banners. Deliberately full-width and unmissable, not tooltips. */}
      <div className="grid gap-px bg-hairline sm:grid-cols-2">
        <ModeBanner
          title="Agent reasoning"
          label={health.agentLlmMode.label}
          state={health.agentLlmMode.state}
          detail={health.agentLlmMode.detail}
        />
        <ModeBanner
          title="Injection classifier"
          label={health.classifierMode.label}
          state={health.classifierMode.state}
          detail={health.classifierMode.detail}
        />
      </div>
    </div>
  );
}

function ModeBanner({
  title,
  label,
  state,
  detail,
}: {
  title: string;
  label: string;
  state: HealthState;
  detail: string;
}) {
  const tone = state === "degraded" ? "approval" : state === "ok" ? "allow" : "neutral";
  return (
    <div
      className={cn(
        "flex flex-col gap-1.5 bg-ink-raised px-4 py-3",
        state === "degraded" && "bg-signal-approval/[0.06]",
      )}
    >
      <div className="flex items-center gap-2">
        <span className="label-xs">{title}</span>
        <Badge tone={tone}>{label}</Badge>
      </div>
      <p className="text-[11px] leading-relaxed text-chalk-muted">{detail}</p>
    </div>
  );
}
