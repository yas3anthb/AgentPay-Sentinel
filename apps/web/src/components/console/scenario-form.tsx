"use client";

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
    <div className="flex flex-col gap-4 p-3">
      <fieldset disabled={disabled} className="flex flex-col gap-1.5">
        <legend className="label-xs mb-1.5">choose a path</legend>
        {SCENARIOS.map((def) => {
          const active = def.id === scenario;
          return (
            <label
              key={def.id}
              className={cn(
                "cursor-pointer rounded-md border px-3 py-2.5 transition-colors",
                // The radio itself is visually hidden, so the label carries the
                // focus ring. Without this, keyboard users get no indication of
                // where they are in the list.
                "has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-signal-idle/70 has-[:focus-visible]:ring-offset-2 has-[:focus-visible]:ring-offset-ink",
                active
                  ? "border-signal-idle/50 bg-signal-idle/[0.07]"
                  : "border-hairline bg-ink-raised/50 hover:border-hairline-bright",
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
                    "h-2 w-2 rotate-45 rounded-[1px] border",
                    active ? "border-signal-idle bg-signal-idle" : "border-chalk-faint",
                  )}
                />
                <span
                  className={cn(
                    "font-mono text-[11px]",
                    active ? "text-signal-idle" : "text-chalk",
                  )}
                >
                  {def.label}
                </span>
                {def.path === null ? <Badge tone="neutral">no agent</Badge> : null}
              </span>
              <span className="mt-1.5 block pl-4 text-[11px] leading-relaxed text-chalk-muted">
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
          <span className="label-xs">instruction to the agent</span>
          <textarea
            value={instruction}
            onChange={(event) => onInstruction(event.target.value)}
            disabled={disabled}
            rows={3}
            className="resize-y rounded border border-hairline bg-ink px-2.5 py-2 font-mono text-[11px] leading-relaxed text-chalk placeholder:text-chalk-faint"
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
    <fieldset disabled={disabled} className="flex flex-col gap-2.5">
      <legend className="label-xs mb-1">hand-crafted payment intent</legend>

      <Text label="merchant" value={raw.merchantId} onChange={(v) => set("merchantId", v)} />
      <div className="grid grid-cols-3 gap-2">
        <Text label="unit price" value={raw.amount} onChange={(v) => set("amount", v)} />
        <Text label="qty" value={String(raw.quantity)} onChange={(v) => set("quantity", Number(v) || 1)} />
        <Text label="currency" value={raw.currency} onChange={(v) => set("currency", v)} />
      </div>
      <Text label="sku" value={raw.sku} onChange={(v) => set("sku", v)} />
      <Text label="purpose" value={raw.purpose} onChange={(v) => set("purpose", v)} />

      <label className="flex flex-col gap-1.5">
        <span className="label-xs">source type</span>
        <select
          value={raw.sourceType}
          onChange={(event) => set("sourceType", event.target.value as RawIntentForm["sourceType"])}
          className="rounded border border-hairline bg-ink px-2.5 py-2 font-mono text-[11px] text-chalk"
        >
          {["official_api", "verified_catalog", "scraped_page", "email", "unknown"].map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="label-xs">merchant content (untrusted)</span>
        <textarea
          value={raw.merchantContent}
          onChange={(event) => set("merchantContent", event.target.value)}
          rows={6}
          className="resize-y rounded border border-hairline bg-ink px-2.5 py-2 font-mono text-[11px] leading-relaxed text-chalk"
        />
        <span className="text-[10px] leading-relaxed text-chalk-faint">
          Paste an attack here. This text reaches the classifier as labelled data inside a
          nonce-delimited block — never as instructions.
        </span>
      </label>
    </fieldset>
  );
}

function Text({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="label-xs">{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="rounded border border-hairline bg-ink px-2.5 py-2 font-mono text-[11px] text-chalk"
      />
    </label>
  );
}
