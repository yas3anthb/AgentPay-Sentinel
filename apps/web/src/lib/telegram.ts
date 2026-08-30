"use client";

import { DEMO } from "@/lib/agents";
import { CONTROL_URL } from "@/lib/config";

/**
 * Telegram account-linking, driven by the control plane. Demo only — a
 * Telegram id is a weak identity, so it is bound to a real AgentPay account
 * through a one-time code the user copies into the bot.
 */

export interface LinkCode {
  code: string;
  expires_at: string;
  expires_in_seconds: number;
}

export interface TelegramStatus {
  linked: boolean;
  telegram_id_masked?: string;
  linked_at?: string;
}

function rec(v: unknown): Record<string, unknown> {
  return typeof v === "object" && v !== null ? (v as Record<string, unknown>) : {};
}

export async function issueLinkCode(): Promise<LinkCode> {
  const response = await fetch(`${CONTROL_URL}/v1/admin/telegram/link-code`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ user_id: DEMO.userId }),
  });
  if (!response.ok) throw new Error(`could not issue a link code: HTTP ${response.status}`);
  const raw = rec(await response.json());
  return {
    code: String(raw.code ?? ""),
    expires_at: String(raw.expires_at ?? ""),
    expires_in_seconds: Number(raw.expires_in_seconds ?? 600),
  };
}

export async function fetchTelegramStatus(): Promise<TelegramStatus> {
  const response = await fetch(
    `${CONTROL_URL}/v1/admin/telegram/status/${encodeURIComponent(DEMO.userId)}`,
    { cache: "no-store" },
  );
  if (!response.ok) return { linked: false };
  const raw = rec(await response.json());
  return {
    linked: raw.linked === true,
    telegram_id_masked:
      typeof raw.telegram_id_masked === "string" ? raw.telegram_id_masked : undefined,
    linked_at: typeof raw.linked_at === "string" ? raw.linked_at : undefined,
  };
}

export async function unlinkTelegram(): Promise<void> {
  const response = await fetch(
    `${CONTROL_URL}/v1/admin/telegram/link/${encodeURIComponent(DEMO.userId)}`,
    { method: "DELETE" },
  );
  if (!response.ok) throw new Error(`unlink failed: HTTP ${response.status}`);
}

export { DEMO };
