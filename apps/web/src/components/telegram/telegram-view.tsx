"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Copy, Info, Link2, Link2Off, Send } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Panel, PanelHeader } from "@/components/ui/panel";
import {
  DEMO,
  fetchTelegramStatus,
  issueLinkCode,
  unlinkTelegram,
  type LinkCode,
  type TelegramStatus,
} from "@/lib/telegram";

const BOT_USERNAME = process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME || "";

export function TelegramView() {
  const [status, setStatus] = useState<TelegramStatus | null>(null);
  const [code, setCode] = useState<LinkCode | null>(null);
  const [remaining, setRemaining] = useState(0);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setStatus(await fetchTelegramStatus());
  }, []);

  useEffect(() => {
    void refresh();
    const id = setInterval(() => void refresh(), 2500);
    return () => clearInterval(id);
  }, [refresh]);

  // Count the issued code down; drop it when it expires.
  useEffect(() => {
    if (!code) return;
    const tick = () => {
      const left = Math.max(0, Math.round((Date.parse(code.expires_at) - Date.now()) / 1000));
      setRemaining(left);
      if (left === 0) setCode(null);
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [code]);

  const generate = async () => {
    setBusy(true);
    setError(null);
    setCopied(false);
    try {
      setCode(await issueLinkCode());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const unlink = async () => {
    setBusy(true);
    setError(null);
    try {
      await unlinkTelegram();
      setCode(null);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked — the code is on screen anyway */
    }
  };

  const deepLink =
    code && BOT_USERNAME ? `https://t.me/${BOT_USERNAME}?start=${code.code}` : null;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start gap-2.5 rounded-panel border border-notice-line bg-notice-tint px-4 py-3">
        <Info size={16} className="mt-0.5 shrink-0 text-notice" />
        <div>
          <p className="text-caption font-medium text-notice">
            Telegram integration — demo only
          </p>
          <p className="mt-0.5 text-caption text-ink-secondary">
            A Telegram user id is a weak identity, so it is bound to this account through a
            one-time code. The bot decides nothing — it calls the same Sentinel gateway this
            console does, and a blocked cart never reaches the payment step. The charge it
            triggers still lands on the mock provider.
          </p>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
        <Panel>
          <PanelHeader
            title="Link a Telegram account"
            subtitle="Generate a code, then send it to the bot from the phone you want to use."
          />
          <div className="flex flex-col gap-4 p-5">
            <ol className="flex flex-col gap-2 text-caption text-ink-secondary">
              <li>1. Generate a one-time code below (valid 10 minutes).</li>
              <li>
                2. In Telegram, open the bot and send it the code
                {BOT_USERNAME ? (
                  <>
                    {" "}
                    — or just tap the <span className="text-ink">t.me</span> link.
                  </>
                ) : null}
              </li>
              <li>
                3. The bot binds that Telegram id to{" "}
                <code className="font-mono text-data text-ink">{DEMO.userId}</code> and runs
                as this account from then on.
              </li>
            </ol>

            <div className="rounded-panel border border-line bg-surface-sunken p-4">
              {code ? (
                <div className="flex flex-col gap-3">
                  <div className="flex items-center justify-between gap-3">
                    <code className="font-mono text-section tracking-wider text-ink">
                      {code.code}
                    </code>
                    <div className="flex items-center gap-2">
                      <Badge tone="neutral">expires in {remaining}s</Badge>
                      <Button size="sm" variant="secondary" onClick={() => copy(code.code)}>
                        {copied ? <Check size={14} /> : <Copy size={14} />}
                        {copied ? "Copied" : "Copy"}
                      </Button>
                    </div>
                  </div>
                  {deepLink ? (
                    <a
                      href={deepLink}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1.5 text-caption text-accent hover:underline"
                    >
                      <Send size={13} /> Open the bot with this code
                    </a>
                  ) : (
                    <p className="text-label text-ink-muted">
                      Set <code className="font-mono">NEXT_PUBLIC_TELEGRAM_BOT_USERNAME</code>{" "}
                      to show a one-tap t.me link.
                    </p>
                  )}
                </div>
              ) : (
                <Button variant="primary" onClick={generate} disabled={busy}>
                  <Link2 size={15} /> Generate link code
                </Button>
              )}
            </div>

            {error ? <p className="text-caption text-block">{error}</p> : null}
          </div>
        </Panel>

        <Panel className="flex flex-col">
          <PanelHeader title="Link status" />
          <div className="flex flex-1 flex-col gap-4 p-5">
            <div className="flex items-center gap-2">
              {status?.linked ? (
                <Badge tone="allow">
                  <Link2 size={12} /> Linked
                </Badge>
              ) : (
                <Badge tone="neutral">
                  <Link2Off size={12} /> Not linked
                </Badge>
              )}
            </div>
            <Field label="Account" value={<code className="font-mono text-data">{DEMO.userId}</code>} />
            <Field
              label="Telegram id"
              value={status?.telegram_id_masked ?? "—"}
              mono
            />
            <Field
              label="Linked at"
              value={
                status?.linked_at
                  ? new Date(status.linked_at).toLocaleString()
                  : "—"
              }
            />
            {status?.linked ? (
              <Button
                variant="destructive"
                size="sm"
                onClick={unlink}
                disabled={busy}
                className="mt-auto self-start"
              >
                <Link2Off size={14} /> Unlink
              </Button>
            ) : null}
          </div>
        </Panel>
      </div>

      <Panel>
        <PanelHeader
          title="What happens in a chat"
          subtitle="The bot is a client of the same endpoints. The protections are inherited, not re-implemented."
        />
        <div className="grid gap-4 p-5 text-caption text-ink-secondary sm:grid-cols-2">
          <div>
            <p className="font-medium text-ink">You send</p>
            <p className="mt-1">
              &ldquo;Restock the office kitchen with coffee. Keep it under 5000 rupees.&rdquo;
            </p>
          </div>
          <div>
            <p className="font-medium text-ink">Bot replies</p>
            <p className="mt-1">
              Shows the cart the agent built, then Sentinel&rsquo;s verdict: a poisoned page
              is <span className="text-block">blocked</span> with no buttons; a clean purchase
              over the threshold shows{" "}
              <span className="text-approval">Approve / Deny</span>.
            </p>
          </div>
          <div>
            <p className="font-medium text-ink">You tap Approve</p>
            <p className="mt-1">
              The bot grants the approval; Sentinel re-checks the exact amount, merchant and
              cart before the token is used, then authorizes.
            </p>
          </div>
          <div>
            <p className="font-medium text-ink">You tap Deny</p>
            <p className="mt-1">Nothing is charged. The pending request is dropped.</p>
          </div>
        </div>
        <div className="border-t border-line px-5 py-3 text-label text-ink-muted">
          Full plan: <code className="font-mono">docs/telegram-integration.md</code>. The bot
          service itself is not part of this build.
        </div>
      </Panel>
    </div>
  );
}
