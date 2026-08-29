"use client";

import { Bot, FileCode2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { RawIntentForm } from "@/lib/run-scenario";
import { SCENARIOS, type Scenario } from "@/lib/store";
import { cn } from "@/lib/utils";

export function ScenarioForm({
  scenario,
  onScenario,
  instruction,
  onInstruction,
  raw,
  onRaw,
  disabled,
}: {
  scenario: Scenario;
  onScenario: (s: Scenario) => void;
  instruction: string;
  onInstruction: (v: string) => void;
  raw: RawIntentForm;
  onRaw: (v: RawIntentForm) => void;
  disabled: boolean;
}) {
  return (
    <div className="flex flex-col gap-5 p-4">
      <fieldset disabled={disabled} className="flex flex-col gap-2">
        <legend className="label mb-1">Choose a scenario</legend>
        {SCENARIOS.map((def) => {
          const active = def.id === scenario;
          return (
            <label
              key={def.id}
              className={cn(
                "cursor-pointer rounded-panel border px-3.5 py-3 transition-colors",
                "has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-accent/45 has-[:focus-visible]:ring-offset-2 has-[:focus-visible]:ring-offset-canvas",
                active
                  ? "border-accent/40 bg-accent-tint"
                  : "border-line bg-surface hover:border-line-strong hover:bg-surface-sunken",
              )}
            >
              <span className="flex items-center gap-2">
                <input
                  type="radio"
                  name="scenario"
                  value={def.id}
                  checked={active}
                  onChange={() => onScenario(def.id)}
                  className="sr-only"
                />
                <span
                  aria-hidden
                  className={cn(
                    "flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2",
                    active ? "border-accent" : "border-line-strong",
                  )}
                >
                  {active ? <span className="h-1.5 w-1.5 rounded-full bg-accent" /> : null}
                </span>
                <span className={cn("text-body font-medium", active ? "text-accent" : "text-ink")}>
                  {def.label}
                </span>
                {def.path === null ? (
                  <Badge tone="neutral" className="ml-auto shrink-0">
                    <FileCode2 size={11} /> No agent
                  </Badge>
                ) : (
                  <Badge tone="neutral" className="ml-auto shrink-0">
                    <Bot size={11} /> Agent
                  </Badge>
                )}
              </span>
              <span className="mt-1.5 block pl-6 text-caption text-ink-secondary">
                {def.description}
              </span>
            </label>
          );
        })}
      </fieldset>

      {scenario === "raw" ? (
        <RawFields raw={raw} onRaw={onRaw} disabled={disabled} />
      ) : (
        <label className="flex flex-col gap-1.5">
          <span className="label">Instruction to the agent</span>
          <textarea
            value={instruction}
            onChange={(event) => onInstruction(event.target.value)}
            disabled={disabled}
            rows={3}
            className="resize-y rounded-control border border-line-strong bg-surface px-3 py-2 text-body text-ink placeholder:text-ink-muted"
          />
        </label>
      )}
    </div>
  );
}

function RawFields({
  raw,
  onRaw,
  disabled,
}: {
  raw: RawIntentForm;
  onRaw: (v: RawIntentForm) => void;
  disabled: boolean;
}) {
  const set = <K extends keyof RawIntentForm>(key: K, value: RawIntentForm[K]) =>
    onRaw({ ...raw, [key]: value });

  return (
    <fieldset disabled={disabled} className="flex flex-col gap-3">
      <legend className="label mb-1">Hand-crafted payment request</legend>

      <Text label="Merchant" value={raw.merchantId} onChange={(v) => set("merchantId", v)} />
      <div className="grid grid-cols-3 gap-2.5">
        <Text label="Unit price" value={raw.amount} onChange={(v) => set("amount", v)} mono />
        <Text
          label="Quantity"
          value={String(raw.quantity)}
          onChange={(v) => set("quantity", Number(v) || 1)}
        />
        <Text label="Currency" value={raw.currency} onChange={(v) => set("currency", v)} mono />
      </div>
      <Text label="SKU" value={raw.sku} onChange={(v) => set("sku", v)} mono />
      <Text label="Purpose" value={raw.purpose} onChange={(v) => set("purpose", v)} />

      <label className="flex flex-col gap-1.5">
        <span className="label">Source type</span>
        <select
          value={raw.sourceType}
          onChange={(event) => set("sourceType", event.target.value as RawIntentForm["sourceType"])}
          className="rounded-control border border-line-strong bg-surface px-3 py-2 text-body text-ink"
        >
          {["official_api", "verified_catalog", "scraped_page", "email", "unknown"].map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="label">Merchant content (untrusted)</span>
        <textarea
          value={raw.merchantContent}
          onChange={(event) => set("merchantContent", event.target.value)}
          rows={6}
          className="resize-y rounded-control border border-line-strong bg-surface px-3 py-2 font-mono text-data text-ink"
        />
        <span className="text-caption text-ink-secondary">
          Paste an attack here. This text reaches the classifier as labelled data — never as
          instructions.
        </span>
      </label>
    </fieldset>
  );
}

function Text({
  label,
  value,
  onChange,
  mono,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  mono?: boolean;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="label">{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={cn(
          "rounded-control border border-line-strong bg-surface px-3 py-2 text-body text-ink",
          mono && "font-mono text-data",
        )}
      />
    </label>
  );
}
