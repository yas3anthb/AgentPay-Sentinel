"use client";

import { useEffect, useState } from "react";

import { Badge, type Tone } from "@/components/ui/badge";
import { fetchStackHealth, type HealthState, type StackHealth } from "@/lib/health";
import { cn } from "@/lib/utils";

const DOT: Record<HealthState, string> = {
  ok: "bg-allow",
  degraded: "bg-approval",
  down: "bg-block",
  unknown: "bg-inactive",
};

const TONE: Record<HealthState, Tone> = {
  ok: "allow",
  degraded: "approval",
  down: "block",
  unknown: "neutral",
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
    return <div className="card px-5 py-4 text-caption text-ink-muted">Checking services…</div>;
  }

  return (
    <div className="card overflow-hidden">
      <div className="grid grid-cols-2 gap-px bg-line sm:grid-cols-3 lg:grid-cols-6">
        {health.services.map((service) => (
          <div key={service.name} className="bg-surface px-4 py-3.5">
            <div className="flex items-center gap-2">
              <span
                className={cn("h-1.5 w-1.5 shrink-0 rounded-full", DOT[service.state])}
                aria-hidden
              />
              <span className="truncate text-caption font-medium text-ink">{service.name}</span>
            </div>
            <p className="mt-1 truncate text-label text-ink-muted" title={service.detail}>
              {service.detail}
            </p>
            <span className="sr-only">status: {service.state}</span>
          </div>
        ))}
      </div>

      {/* Mode banners. Deliberately full-width and unmissable, not tooltips. */}
      <div className="grid gap-px bg-line sm:grid-cols-2">
        <ModeBanner
          title="Agent reasoning"
          label={health.agentLlmMode.label}
          state={health.agentLlmMode.state}
          detail={health.agentLlmMode.detail}
        />
        <ModeBanner
          title="Content classifier"
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
  return (
    <div className="flex flex-col gap-1.5 bg-surface px-5 py-3.5">
      <div className="flex items-center gap-2">
        <span className="label">{title}</span>
        <Badge tone={TONE[state]}>{label}</Badge>
      </div>
      <p className="text-caption text-ink-secondary">{detail}</p>
    </div>
  );
}
