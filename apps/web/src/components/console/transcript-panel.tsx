"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  Bot,
  ClipboardCheck,
  Fingerprint,
  Info,
  ScrollText,
  Wrench,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Badge, DecisionPill, OriginPill } from "@/components/ui/badge";
import type { RunSummary, TranscriptStep } from "@/lib/api/transcript";
import { cn, formatMs, shortHash } from "@/lib/utils";

const KIND_META: Record<string, { label: string; icon: typeof Bot }> = {
  graph_transition: { label: "Workflow step", icon: ScrollText },
  agent_step: { label: "Agent reasoning", icon: Bot },
  tool_call: { label: "Tool call", icon: Wrench },
  tool_result: { label: "Tool result", icon: Wrench },
  gateway_decision: { label: "Sentinel decision", icon: ClipboardCheck },
  review: { label: "Review", icon: ClipboardCheck },
  error: { label: "Error", icon: AlertTriangle },
  note: { label: "Note", icon: Info },
};

function metaFor(kind: string) {
  return KIND_META[kind] ?? { label: kind, icon: Info };
}

/** First letter capitalised, nothing else changed — the API already writes
 * plain sentence fragments; this just makes them read as sentences. */
function sentenceCase(text: string): string {
  if (!text) return text;
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function TranscriptPanel({
  run,
  reducedMotion,
}: {
  run: RunSummary;
  reducedMotion: boolean;
}) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth" });
  }, [run.transcript.steps.length, reducedMotion]);

  return (
    <div className="flex min-h-0 flex-col">
      {run.simulated_reasoning ? <SandboxBanner warning={run.warning} /> : null}

      <ol className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-4">
        <AnimatePresence initial={false}>
          {run.transcript.steps.map((step) => (
            <motion.li
              key={`${step.index}-${step.name}`}
              initial={reducedMotion ? false : { opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.18 }}
            >
              <StepCard step={step} />
            </motion.li>
          ))}
        </AnimatePresence>
        <div ref={endRef} />
      </ol>
    </div>
  );
}

/** A calm "sandbox mode" notice — not a terminal warning block, and never
 * amber, since amber is reserved for REQUIRE_APPROVAL. */
function SandboxBanner({ warning }: { warning?: string }) {
  return (
    <div className="flex items-start gap-2.5 border-b border-notice-line bg-notice-tint px-4 py-3">
      <Info size={16} className="mt-0.5 shrink-0 text-notice" />
      <div>
        <p className="text-caption font-medium text-notice">
          Sandbox mode — agent reasoning is scripted
        </p>
        <p className="mt-0.5 text-caption text-ink-secondary">
          {warning ??
            "The agent's reasoning steps below follow a fixed script rather than a language model. Every scripted step is marked. The Sentinel decisions, reason codes and audit hashes are real."}
        </p>
      </div>
    </div>
  );
}

function StepCard({ step }: { step: TranscriptStep }) {
  const [open, setOpen] = useState(false);
  const { label, icon: Icon } = metaFor(step.kind);
  const isGateway = step.kind === "gateway_decision";
  const isError = step.kind === "error";
  const evidence = injectionEvidence(step);
  const reasonCodes = isGateway ? asStringArray(step.detail.reason_codes) : [];
  const detailEntries = Object.entries(step.detail).filter(
    ([key]) => !["content", "content_sha256", "is_known_injection_payload", "reason_codes"].includes(key),
  );

  return (
    <div
      className={cn(
        "rounded-panel border px-4 py-3",
        isGateway
          ? "border-accent/25 bg-accent-tint/40"
          : isError
            ? "border-block-line bg-block-tint/40"
            : "border-line bg-surface",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-2.5">
          <Icon size={16} className="mt-0.5 shrink-0 text-ink-muted" aria-hidden />
          <div className="min-w-0">
            <p className={cn("text-body", isGateway ? "font-medium text-ink" : "text-ink")}>
              {sentenceCase(step.summary) || label}
            </p>
            <p className="mt-0.5 text-label text-ink-muted">
              {label}
              {step.actor ? ` · ${step.actor}` : ""}
              {step.latency_ms !== null ? ` · ${formatMs(step.latency_ms)}` : ""}
            </p>
          </div>
        </div>
        {/* Consistent corner position, every card, always. */}
        <OriginPill simulated={step.simulated} className="shrink-0" />
      </div>

      {reasonCodes.length ? (
        <div className="ml-6 mt-2.5 flex flex-wrap gap-1.5">
          <DecisionPill decision={step.name} />
          {reasonCodes.map((code) => (
            <Badge key={code} tone="neutral" className="font-mono normal-case tracking-normal">
              {code}
            </Badge>
          ))}
        </div>
      ) : null}

      {evidence ? <InjectionEvidenceCard {...evidence} /> : null}

      {detailEntries.length > 0 ? (
        <div className="ml-6 mt-2">
          <button
            onClick={() => setOpen((v) => !v)}
            className="text-caption font-medium text-accent hover:text-accent-hover"
          >
            {open ? "Hide details" : "View details"}
          </button>
          {open ? (
            <pre className="mt-2 max-h-48 overflow-auto rounded-control border border-line bg-surface-sunken p-2.5 font-mono text-data text-ink-secondary">
              {JSON.stringify(Object.fromEntries(detailEntries), null, 2)}
            </pre>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

function injectionEvidence(
  step: TranscriptStep,
): { hash: string; known: boolean } | null {
  if (step.name !== "fetch_merchant_page") return null;
  const hash = step.detail.content_sha256;
  if (typeof hash !== "string") return null;
  return { hash, known: step.detail.is_known_injection_payload === true };
}

/**
 * The injection-integrity callout, as a labelled evidence card rather than
 * inline red text. This is the strongest proof the product has that an
 * attack reached the agent unmodified, so it gets its own clearly bounded
 * space instead of being folded into the log.
 */
function InjectionEvidenceCard({ hash, known }: { hash: string; known: boolean }) {
  return (
    <div
      className={cn(
        "ml-6 mt-2.5 rounded-control border px-3 py-2.5",
        known ? "border-block-line bg-block-tint" : "border-line bg-surface-sunken",
      )}
    >
      <div className="flex items-center gap-2">
        <Fingerprint size={14} className={known ? "text-block" : "text-ink-muted"} aria-hidden />
        <span className={cn("text-caption font-medium", known ? "text-block" : "text-ink-secondary")}>
          {known ? "Known injection payload" : "Content hash recorded"}
        </span>
      </div>
      <p className="mt-1 text-label text-ink-muted">Content hash (SHA-256)</p>
      <code className="block truncate font-mono text-data text-ink-secondary">
        {shortHash(hash, 40)}
      </code>
      <p className="mt-1.5 text-caption text-ink-secondary">
        Hashed at the moment the agent read this page. Nothing upstream altered the content
        before it reached this point.
      </p>
    </div>
  );
}
