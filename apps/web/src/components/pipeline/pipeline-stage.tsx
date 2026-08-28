"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

import { StageList2D } from "@/components/pipeline/stage-list-2d";
import { Badge } from "@/components/ui/badge";
import type { PipelineState } from "@/lib/pipeline";
import type { RunPhase } from "@/lib/store";
import { useWebGLAvailable } from "@/lib/use-stage-events";

// Three.js is heavy and only ever runs in the browser.
const Scene3D = dynamic(
  () => import("@/components/pipeline/scene-3d").then((m) => m.Scene3D),
  { ssr: false, loading: () => <SceneSkeleton /> },
);

/**
 * Picks the renderer.
 *
 * The 2D list is a genuine fallback, not a placeholder: it shows the same
 * stages, the same statuses, the same real latencies, and the same severance
 * point. Nothing about the product requires WebGL to be usable.
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
  const [forced2D, setForced2D] = useState(false);
  const idle = phase === "idle";

  // A WebGL context can be lost at runtime, not just refused at startup.
  useEffect(() => {
    const onLost = () => setForced2D(true);
    window.addEventListener("webglcontextlost", onLost);
    return () => window.removeEventListener("webglcontextlost", onLost);
  }, []);

  if (webgl === null) return <SceneSkeleton />;

  if (!webgl || forced2D) {
    return (
      <div className="p-4">
        <div className="mb-3 flex items-center gap-2">
          <Badge tone="neutral">2D view</Badge>
          <span className="text-[11px] text-chalk-muted">
            {forced2D
              ? "The WebGL context was lost, so the same data is rendered here."
              : "WebGL is unavailable in this browser. The same data is rendered here."}
          </span>
        </div>
        <StageList2D state={state} reducedMotion={reducedMotion} />
      </div>
    );
  }

  return (
    <div className="relative h-[400px] w-full" aria-hidden="true">
      {/* Decorative for assistive tech: the same information is available in
          the Stages list below, which is a real list with real text. */}
      <Scene3D state={state} reducedMotion={reducedMotion} idle={idle} />
      {reducedMotion ? (
        <span className="pointer-events-none absolute bottom-3 left-4 font-mono text-[9px] uppercase tracking-wider text-chalk-faint">
          reduced motion — animation disabled, state still live
        </span>
      ) : null}
    </div>
  );
}

function SceneSkeleton() {
  return (
    <div className="flex h-[400px] items-center justify-center font-mono text-[11px] text-chalk-faint">
      preparing scene…
    </div>
  );
}
