"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { Box } from "lucide-react";

import { EffectBoundary } from "@/components/effects/effect-boundary";
import { StepTracker } from "@/components/pipeline/step-tracker";
import { Button } from "@/components/ui/button";
import type { PipelineState } from "@/lib/pipeline";
import type { RunPhase } from "@/lib/store";
import { useWebGLAvailable } from "@/lib/use-stage-events";
import { cn } from "@/lib/utils";

// Three.js is heavy and only ever runs in the browser.
const Scene3D = dynamic(
  () => import("@/components/pipeline/scene-3d").then((m) => m.Scene3D),
  { ssr: false, loading: () => <SceneSkeleton /> },
);

/**
 * The step tracker is the product's primary view of the pipeline — it needs
 * no WebGL and reads at a glance. The 3D scene is an optional, restyled
 * companion view behind a toggle, off by default. Both render the exact same
 * `PipelineState`; nothing about what is shown changes with the toggle, only
 * how it is rendered. If WebGL is unavailable, or its context is lost mid
 * session, the toggle disables itself rather than failing silently.
 */
export function PipelineStage({
  state,
  reducedMotion,
  phase,
}: {
  state: PipelineState;
  reducedMotion: boolean;
  phase: RunPhase;
}) {
  const webgl = useWebGLAvailable();
  const [lost, setLost] = useState(false);
  const [crashed, setCrashed] = useState(false);
  const [show3D, setShow3D] = useState(false);
  const idle = phase === "idle";
  const canShow3D = webgl === true && !lost && !crashed;

  useEffect(() => {
    const onLost = () => {
      setLost(true);
      setShow3D(false);
    };
    window.addEventListener("webglcontextlost", onLost);
    return () => window.removeEventListener("webglcontextlost", onLost);
  }, []);

  return (
    <div>
      <div className="flex items-center justify-between border-b border-line px-5 py-2.5">
        <span className="text-caption text-ink-secondary">
          {show3D && canShow3D ? "3D visualization" : "Step-by-step view"}
        </span>
        <Button
          size="sm"
          variant={show3D && canShow3D ? "secondary" : "ghost"}
          onClick={() => setShow3D((v) => !v)}
          disabled={!canShow3D}
          title={
            canShow3D
              ? undefined
              : lost
                ? "The 3D context was lost; showing the step view instead."
                : crashed
                  ? "The 3D view failed to render; showing the step view instead."
                  : webgl === false
                    ? "WebGL is unavailable in this browser."
                    : undefined
          }
        >
          <Box size={14} />
          {show3D && canShow3D ? "Hide 3D view" : "3D view"}
        </Button>
      </div>

      {show3D && canShow3D ? (
        <div className="relative h-[360px] w-full bg-surface-sunken" aria-hidden="true">
          {/* Decorative for assistive tech: the step tracker above/below carries
              the same information as real, readable text. It's also the
              fallback here — if the 3D scene throws for any reason (a
              vendored dependency incompatibility, a browser quirk), the
              boundary reverts the toggle and the tracker takes over rather
              than leaving a dead panel on screen. */}
          <EffectBoundary
            onError={() => {
              setCrashed(true);
              setShow3D(false);
            }}
          >
            <Scene3D state={state} reducedMotion={reducedMotion} idle={idle} />
          </EffectBoundary>
          {reducedMotion ? (
            <span className="pointer-events-none absolute bottom-3 left-4 text-label text-ink-muted">
              Reduced motion — animation disabled, data still live
            </span>
          ) : null}
        </div>
      ) : (
        <StepTracker state={state} reducedMotion={reducedMotion} />
      )}
    </div>
  );
}

function SceneSkeleton() {
  return (
    <div className={cn("flex h-[360px] items-center justify-center bg-surface-sunken")}>
      <span className="text-caption text-ink-muted">Preparing 3D scene…</span>
    </div>
  );
}
