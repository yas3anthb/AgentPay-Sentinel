"use client";

import dynamic from "next/dynamic";

import { EffectBoundary } from "@/components/effects/effect-boundary";
import { usePrefersReducedMotion, useWebGLAvailable } from "@/lib/use-stage-events";

// PixelBlast is a WebGL effect and has no prefers-reduced-motion handling of
// its own — that's handled entirely here, by not mounting it at all rather
// than trying to freeze an animation loop we don't own.
const PixelBlast = dynamic(() => import("./PixelBlast"), { ssr: false });

/**
 * The Overview page's ambient background, and only the Overview page's — the
 * Test Console and Audit pages carry dense real data and need a flat, calm
 * canvas to stay legible, so this component is deliberately not reused there.
 *
 * Tuned down from PixelBlast's flashy defaults — slow speed, square pixels
 * (the calmest of its four shape options), no ripples/liquid distortion — but
 * tuned UP from an earlier pass that erred too far the other way: indigo dots
 * at 12% opacity on the light canvas were effectively invisible, since the
 * shader's own Bayer-dithered coverage is already sparse before CSS opacity
 * multiplies on top of it. The values below were checked against an actual
 * rendered screenshot, not just read off as numbers.
 */
export function AmbientBackground() {
  const reducedMotion = usePrefersReducedMotion();
  const webgl = useWebGLAvailable();

  // No motion preference, or no WebGL: render nothing. The hero copy and
  // layout underneath already stand on their own without this texture.
  if (reducedMotion || webgl === false || webgl === null) return null;

  return (
    <div className="pointer-events-none absolute inset-0 opacity-[0.28]" aria-hidden="true">
      {/* A decorative background must never be able to take the page down.
          If this vendored WebGL effect throws for any reason — a future
          three.js bump, a browser quirk, anything — the boundary swallows it
          and falls back to nothing, leaving the calm solid canvas colour
          underneath exactly as it already is. */}
      <EffectBoundary>
        <PixelBlast
          variant="square"
          color="#4338CA"
          pixelSize={4}
          patternScale={2.6}
          patternDensity={0.85}
          speed={0.18}
          enableRipples={false}
          liquid={false}
          edgeFade={0.5}
          transparent
          autoPauseOffscreen
        />
      </EffectBoundary>
    </div>
  );
}
