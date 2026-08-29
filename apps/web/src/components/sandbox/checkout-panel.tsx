"use client";

import dynamic from "next/dynamic";
import { CheckCircle2, CircleDashed, Loader2, ShieldOff, XCircle } from "lucide-react";

import { EffectBoundary } from "@/components/effects/effect-boundary";
import { CHECKOUT_STEPS, type CheckoutStep } from "@/lib/checkout-sandbox";
import { useWebGLAvailable } from "@/lib/use-stage-events";
import { cn } from "@/lib/utils";

const CheckoutScene3D = dynamic(
  () => import("./checkout-scene-3d").then((m) => m.CheckoutScene3D),
  { ssr: false, loading: () => <div className="h-[260px] bg-[#EEF4FF]" /> },
);

const ICONS: Record<string, typeof CheckCircle2> = {
  order_created: CircleDashed,
  method_selected: CircleDashed,
  authenticating: Loader2,
  captured: CheckCircle2,
};

/**
 * The simulated checkout, in whichever renderer the browser can support.
 *
 * This never claims to be a real Razorpay integration — see the banner in
 * SandboxView. What IS real: the state driving this panel comes straight from
 * the actual Sentinel decision (`useCheckoutSandbox`), so a blocked run never
 * reaches this panel at all, and an approval pause here is the same real
 * pause the Test Console shows, not a scripted delay.
 */
export function CheckoutPanel({
  step,
  reducedMotion,
}: {
  step: CheckoutStep;
  reducedMotion: boolean;
}) {
  const webgl = useWebGLAvailable();

  if (step === "idle") {
    return (
      <div className="flex h-[260px] items-center justify-center bg-[#EEF4FF]">
        <p className="text-caption text-ink-muted">Run a scenario to see the checkout.</p>
      </div>
    );
  }

  if (step === "not_reached") {
    return (
      <div className="flex h-[260px] flex-col items-center justify-center gap-2 bg-block-tint">
        <ShieldOff size={22} className="text-block" />
        <p className="text-caption font-medium text-block">
          Blocked before checkout — Razorpay was never contacted
        </p>
      </div>
    );
  }

  const showScene = webgl === true;

  return (
    <div className="relative h-[260px] w-full bg-[#EEF4FF]" aria-hidden="true">
      {showScene ? (
        <EffectBoundary fallback={<CheckoutSteps2D step={step} />}>
          <CheckoutScene3D step={step} reducedMotion={reducedMotion} />
        </EffectBoundary>
      ) : (
        <CheckoutSteps2D step={step} />
      )}
    </div>
  );
}

/** The 2D fallback — same steps, same outcome, no WebGL required. */
function CheckoutSteps2D({ step }: { step: CheckoutStep }) {
  const activeIndex =
    step === "declined" ? 3 : CHECKOUT_STEPS.findIndex((s) => s.id === step);

  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 px-6">
      <div className="flex items-center gap-3">
        {CHECKOUT_STEPS.map((s, i) => {
          const Icon = ICONS[s.id];
          const isDeclineHere = step === "declined" && i === 3;
          const active = i <= activeIndex;
          return (
            <div key={s.id} className="flex items-center gap-3">
              <div className="flex flex-col items-center gap-1.5">
                <span
                  className={cn(
                    "flex h-9 w-9 items-center justify-center rounded-panel border-2",
                    isDeclineHere
                      ? "border-block bg-block-tint text-block"
                      : active
                        ? "border-[#2563EB] bg-[#2563EB]/10 text-[#2563EB]"
                        : "border-line bg-surface text-ink-muted",
                  )}
                >
                  {isDeclineHere ? (
                    <XCircle size={16} />
                  ) : (
                    <Icon size={16} className={s.id === "authenticating" && active ? "animate-spin" : ""} />
                  )}
                </span>
                <span className="text-label text-ink-muted">{s.label}</span>
              </div>
              {i < CHECKOUT_STEPS.length - 1 ? (
                <span className={cn("h-0.5 w-8 rounded-full", active && i < activeIndex ? "bg-[#2563EB]" : "bg-line-strong")} />
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
