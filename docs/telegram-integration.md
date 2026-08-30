# Telegram Integration — Demo Only

> **DEMO ONLY.** This is a thin client for the demo. It is not a production
> channel. A Telegram user id is a weak identity, the allow-list is small, and
> the payment it triggers still lands on the mock provider. The bot **decides
> nothing** — it asks the Sentinel gateway and shows the answer.

> **Secret handling.** The bot token is read from `TELEGRAM_BOT_TOKEN` (env
> only, never committed — `.env` is git-ignored). If a token was ever pasted
> in plaintext anywhere, revoke it in **@BotFather → /mybots → API Token →
> Revoke** and issue a new one.

---

## What it does

The flow a registered user sees:

1. User messages the bot: *"Restock the office kitchen with coffee. Keep it under five thousand rupees."*
2. Bot replies *"working…"*, runs the real CrewAI agent through Sentinel.
3. Bot shows the cart the agent built: item, quantity, price, merchant.
4. Sentinel's verdict decides what happens next:
   - **BLOCK** (e.g. a poisoned product page) → bot shows *"blocked: <reason codes>, no payment made"*. No buttons.
   - **REQUIRE_APPROVAL** → bot shows the bound amount/merchant and two buttons: **Approve / Deny**.
5. **Approve** → bot grants the approval, the payment is authorized and charged (mock provider).
6. **Deny** → nothing happens.

Everything the web console protects against still applies, because the bot uses
the same endpoints.

---

## Architecture

A new stand-alone service, same pattern as `apps/event-relay/` — small, single
job, out of the payment path.

```
Telegram  ──HTTPS webhook──▶  telegram-bot (:9400)
                                  │
                                  ├─▶ control-plane :8090   (link code -> resolve user, X-Admin-Key)
                                  ├─▶ agent-simulator :9200  (/simulate/* — run the agent)
                                  └─▶ gateway :8080          (/v1/approvals/{id}, /grant)
```

- The bot holds **no delegation token and no admin key of its own** beyond what
  it needs to call the control-plane link endpoint. It never calls
  `/v1/payment-intents` directly with authority it minted.
- It is a client of the same APIs the web console uses. No change to
  `gateway/`, `control_plane/`, or `policies/`.

### Getting updates from Telegram

Two options; pick per environment:

| Mode | Use when | How |
|---|---|---|
| **Long polling** | local demo, laptop | bot calls `getUpdates` in a loop. No public URL needed. |
| **Webhook** | deployed demo | Telegram POSTs to `https://<host>/tg/<secret-path>`. Needs HTTPS (ngrok for a laptop demo). |

Default the demo to **long polling** so there is nothing to expose.

---

## The conversation, step by step

### Linking (once per user)

1. Web console (`/agents` or a new "Telegram Integration" tab) shows a one-time
   code, e.g. `LINK-7F3K`, valid ~10 minutes, single use.
2. User sends `/start` then `LINK-7F3K` to the bot.
3. Bot calls `POST /v1/admin/telegram/link` on the control-plane (new endpoint,
   see below) with `{ code, telegram_id }`.
4. Control-plane validates the code, stores `telegram_id -> user_id`, marks the
   code spent, returns the resolved `user_id` and `delegation_id`.
5. Bot: *"Linked to account user_ada. You can now ask me to buy things."*

Unlinked or unknown ids get *"You are not registered. Get a link code from the console."*

### A purchase

```
User:  Restock the office kitchen with coffee. Keep it under 5000 rupees.

Bot:   🔍 Working… (the agent is researching)

Bot:   Here is what the agent wants to buy:
       • Ethiopian whole bean 1kg × 2 — ₹2,400
       Merchant: The Beanery (verified)
       Sentinel is checking it…

   ── if BLOCK ──
Bot:   🚫 Blocked by policy — PROMPT_INJECTION_HIGH_CONFIDENCE
       No payment was made. The provider was never contacted.
       Audit: 169bfd59…

   ── if REQUIRE_APPROVAL ──
Bot:   🟡 Approval needed
       Amount: ₹2,400 · Merchant: The Beanery · Cart a3f9…
       [ ✅ Approve ]   [ ❌ Deny ]

User:  (taps ✅ Approve)

Bot:   ✅ Approved and paid.
       State: CONFIRMED · Ref: ch_6900b83b · Audit: 7b868638…
```

---

## Endpoints reused (no Sentinel changes)

| Purpose | Call |
|---|---|
| Run the agent for an instruction | `POST {SIMULATOR}/simulate/clean-purchase` `{instruction, budget}` |
| (attack demo) | `POST {SIMULATOR}/simulate/adversarial` |
| What a human is being asked to approve | `GET {GATEWAY}/v1/approvals/{id}` |
| Grant the approval | `POST {GATEWAY}/v1/approvals/{id}/grant` → returns `approval_token` |
| Resubmit with the token (done by the agent graph on resume) | via `POST {SIMULATOR}/simulate/{run_id}/approve` |

The simulator already returns the full transcript (cart, decision, reason
codes, audit hash) and now also `request_id` — the bot can quote all of it.

---

## New pieces

### Done in this repo

2. **Control-plane link endpoints** (`control_plane/telegram.py` + routes) —
   `X-Admin-Key` gated, admin-audited, cleared by `dev/reset`:
   - `POST /v1/admin/telegram/link-code` `{user_id}` → one-time code, 10-min TTL, single-use
   - `POST /v1/admin/telegram/link` `{code, telegram_id}` → binds, returns `user_id`; 404 / 409 / 410 on bad code
   - `GET  /v1/admin/telegram/status/{user_id}` → linked?, masked id, linked_at
   - `DELETE /v1/admin/telegram/link/{user_id}` → unlink
   - tables `telegram_links`, `telegram_link_codes`; covered by `tests/test_control_plane.py`
3. **Web "Telegram" tab** — `/telegram` (`apps/web/src/app/telegram/`,
   `components/telegram/telegram-view.tsx`, `lib/telegram.ts`), nav entry added:
   - **Demo only** banner, *Generate link code* with a live countdown, copy button
   - link status (linked / not linked, masked id)
   - a one-tap `t.me/<bot>?start=<code>` link when `NEXT_PUBLIC_TELEGRAM_BOT_USERNAME` is set
   - an explainer of the chat flow

1. **`apps/telegram-bot/`** — the bot service, built:
   - `config.py` · `api.py` (tiny raw Bot API client, no third-party lib) ·
     `backend.py` (calls control-plane + simulator) · `handlers.py` (routing +
     formatting, pure and unit-tested) · `main.py` (long-poll loop) ·
     `webapp.py` (webhook mode)
   - commands: `/start`, `/help`, `/status`, a bare `LINK-XXXXXX` code,
     `/attack` (adversarial scenario), any other text = purchase instruction
   - `REQUIRE_APPROVAL` → inline **Approve / Deny** buttons; Approve resumes the
     run via `/simulate/{run_id}/approve`; a **BLOCK never shows buttons**
   - 11 handler tests (`apps/telegram-bot/tests/`), Telegram + backends faked
   - compose service `telegram-bot` behind the `telegram` **profile** (opt-in),
     long-polling, no port; `make telegram-up` / `telegram-logs` / `telegram-down`

## Running the bot

```bash
# 1. Put the REAL token in .env (git-ignored). Never anywhere else.
echo 'TELEGRAM_BOT_TOKEN=<from @BotFather>' >> .env
echo 'TELEGRAM_BOT_USERNAME=AgentPayyashh_bot' >> .env

# 2. Start the stack, then the bot
make up
make telegram-up
make telegram-logs        # should print: bot @AgentPayyashh_bot online (polling)
```

Then in Telegram: open the bot → `/start` → paste a `LINK-XXXX` code from the
web **Telegram** tab → send *"Restock the office kitchen with coffee, under
5000 rupees"* → cart + **Approve / Deny** → tap Approve.

---

## Data model

One table, on the shared DB (owned by the control-plane, like the other
registry tables):

```
telegram_links
  telegram_id   BIGINT   primary key
  user_id       TEXT     not null            -- the AgentPay account
  linked_at     TIMESTAMP
telegram_link_codes
  code          TEXT     primary key
  user_id       TEXT     not null
  created_at    TIMESTAMP
  used_at       TIMESTAMP nullable            -- single use
```

Code rules: 8 chars, expire after 10 minutes, one use, deleted after link.

---

## Config

```
# apps/telegram-bot
TELEGRAM_BOT_TOKEN=            # from @BotFather, env only, never committed
TELEGRAM_MODE=polling         # polling | webhook
TELEGRAM_WEBHOOK_URL=         # only if mode=webhook
TELEGRAM_ALLOWLIST=           # optional hard allow-list of telegram ids for the demo
GATEWAY_URL=http://gateway:8080
SIMULATOR_URL=http://agent-simulator:9200
CONTROL_PLANE_URL=http://control-plane:8090
ADMIN_API_KEY=dev-admin-key   # only for the link endpoints
```

`docker-compose.yml`: add a `telegram-bot` service (`build: .` with a
`command:` override, or its own small image), `depends_on` gateway +
control-plane healthy, `ports: ["9400:9400"]` only if webhook mode.

---

## Trust rules (keep these true)

- The bot **never decides** an outcome. It calls Sentinel and renders the
  verdict. No local allow/deny logic on payments.
- The **Approve button carries the exact `approval_request_id`**. Sentinel
  re-checks amount / merchant / currency / cart hash when the token is used, so
  the bot cannot substitute a different purchase after approval.
- A Telegram id is treated as a **convenience identity**. In production it maps
  to a real authenticated account; say so in the demo.
- The bot token is a secret. Env only. Revoke + reissue if leaked.
- Link codes are one-time and short-lived.
- The bot has **no** payment credential and cannot reach the provider.

---

## What is real vs mock in this integration

| Real | Mock / demo-grade |
|---|---|
| The agent run (CrewAI + LangGraph) | The final charge (mock provider) |
| All 7 Sentinel stages, the policy decision, reason codes | Telegram id as identity |
| The approval binding and re-check | The allow-list |
| The audit hash chain | — |
| The block on a poisoned page | — |

To make the charge real later: replace the mock-provider call in stage 6 with
**Telegram Bot Payments** — send an invoice, and answer the
`pre_checkout_query` webhook `ok: true` **only if** Sentinel returned ALLOW.
Sentinel's `UNKNOWN → reconcile → CONFIRMED/FAILED` state machine maps onto
`successful_payment` / timeout. That is the same gate point, no architecture
change.

---

## Demo script (2 minutes)

1. Show the web console `/telegram` tab → **Generate link code** → tap the
   `t.me` deep link on your phone → bot says *linked*.
2. On the phone: *"Restock the office kitchen with coffee, under 5000 rupees."*
3. Bot shows the cart → **Approval needed** with the amount → tap **Approve** →
   *paid, CONFIRMED, audit hash*.
4. Now send a line that simulates the attack path (or use `/attack` to call
   `/simulate/adversarial`): bot shows **🚫 Blocked — prompt injection, no
   payment, provider never contacted.**
5. Point back at the web `/audit` page → the chain still verifies, both
   decisions are in it.

Line to say: *"Same gateway, same policy, same audit trail — Telegram is just
another client, and it still can't get a poisoned cart past Sentinel."*

---

## Effort

| Piece | Rough size | Status |
|---|---|---|
| control-plane link endpoints + tables + tests | ~2 hours | **done** |
| web `/telegram` tab + nav entry | ~2 hours | **done** |
| compose env wiring | ~15 min | **done** |
| `apps/telegram-bot` service | ~1 day | to build |

No changes to `gateway/`, `policies/`, or the pipeline.
