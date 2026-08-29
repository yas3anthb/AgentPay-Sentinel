# AgentPay Sentinel — Web

The product frontend. Next.js 14 (App Router) + TypeScript, talking to the
Sentinel gateway, the CrewAI agent simulator, and the pipeline event relay.

```bash
docker compose up -d --build     # from the repo root — starts everything
open http://localhost:3000
```

For local development against a running stack:

```bash
npm install
npm run gen:api    # regenerate typed clients from both live OpenAPI schemas
npm run dev
```

## The rule this UI is built around

**Render what actually happened.** Every visual claim traces to data from a
real service, and where the data is scripted rather than live, the interface
says so — permanently, not in a tooltip.

- **Scripted vs live steps.** The agent simulator tags each transcript step
  `simulated: true/false`. A scripted step gets a violet left border, a violet
  tint, and a `scripted` badge; a live step gets `live`. They are never styled
  the same. When the parser cannot tell, it defaults to *scripted* — the honest
  direction to fail in.
- **Offline banner.** When `AGENT_LLM_MODE=offline`, the transcript is headed
  by an amber "Offline / scripted reasoning — Sentinel decisions are live"
  banner. The distinction matters: in offline mode the agent's reasoning is a
  script, but the decision, reason codes and audit hashes came from the real
  gateway, and those steps are marked live inside a scripted run.
- **Failures stay failures.** A 502 from `/simulate/*` renders the raw error
  code and message with an explicit note that no run happened. The console
  never synthesizes a transcript to fill the screen.
- **Timing is measured, not scripted.** The 3D scene is driven by stage events
  the gateway publishes at each real stage boundary. If the OpenAI classifier
  takes 400ms, the visualisation waits 400ms.
- **The classifier mode is not guessed.** The gateway does not publish it on
  `/readyz`, so the Overview strip says exactly that instead of inventing a
  badge. The Test Console reports the real value per transaction, read from
  `risk.signals.classifier_degraded` in the decision.

## Pages

| Route | |
|---|---|
| `/` | Pitch, live service strip, idle pipeline preview |
| `/test` | The demo: four scenarios, 3D pipeline, transcript, decision |
| `/agents` | Delegation, spending limits, revocation, demo reset |
| `/audit` | Hash-chain verification and a read-only Rego viewer |

### `/test` — the four paths

Three run through the real CrewAI agent; the fourth bypasses it entirely so a
judge can probe the policy engine on its own.

| Selector | Goes to |
|---|---|
| Clean purchase | `POST /simulate/clean-purchase` |
| Adversarial (injected merchant content) | `POST /simulate/adversarial` |
| Approval-required | `POST /simulate/approval-flow` |
| Raw payment intent | `POST /v1/payment-intents` — no agent in the loop |

The approval scenario shows an explicit **"paused — awaiting approval"** state
with Approve/Deny actions, never a spinner: the LangGraph run really is stopped
on an `interrupt_before`, and nothing is polling while it waits.

### The containment cross-check

On a blocked adversarial run the console makes two claims from **two
independent sources**:

1. gateway stage events say the authorization stage was never reached
   (`token_issued: false`, `provider_contacted: false`) — this is what the
   severed beam draws;
2. the mock provider's own call counter reports a delta of `0`.

`ConsistencyCheck` compares them and prints "sources agree" — or, if they ever
disagree, a red warning telling you not to trust the visualisation for that
run. A visualisation that lies about containment is the worst failure this UI
could have, so it checks rather than assumes.

## The 3D scene

Seven nodes, one distinct abstract form each — a torus for identity, an
icosahedron for the LLM classifier (the only shape that idles with a spin), a
subdivided lattice for OPA, a torus knot for the audit chain. Emissive
wireframes on a near-black ground; no default lighting rig, no default
materials.

- **Green** pass-through, **amber** pause, **red** severed beam.
- The beam physically stops at the blocking node and later segments go dashed
  and dim.
- **The audit node still lights up after a block.** Every decision is recorded,
  so drawing the ledger dark would be a prettier animation and a false one.
- Events carry a monotonic `seq` assigned when the stage boundary was crossed,
  because fire-and-forget publishes can arrive out of order. The reducer sorts
  by it; sorting by arrival would render a plausible but wrong sequence.

**Fallback and motion.** No WebGL — or a context lost at runtime — falls back
to a framer-motion stage list with the same stages, statuses, real latencies
and severance point. `prefers-reduced-motion` disables the idle camera drift
and the pulse animations while the state stays live. The canvas is
`aria-hidden`; the same information lives in the adjacent list as real text,
and run outcomes are announced through an `aria-live` region.

## Architecture notes

**Both backends are proxied server-side** through route handlers at
`/api/gateway/*` and `/api/simulator/*`. Two reasons: the gateway has no CORS
middleware and adding one would mean editing a deny-by-default payment service
to suit a frontend; and route handlers read service origins per request, so one
image runs locally and in Compose. (This started as `next.config` rewrites —
those are frozen into the routes manifest at build time, so the container
proxied to its own localhost.)

The relay WebSocket is **not** proxied: WebSockets bypass CORS anyway.

**Typed clients** are generated from both live OpenAPI schemas by
`npm run gen:api` into `src/lib/api/schema/`. One caveat worth knowing: the
simulator's `/simulate/*` handlers are annotated `-> dict`, so its schema
declares those responses as a bare object and there is nothing richer to
generate. Paths and request bodies are fully typed; the response *shape* is
parsed and narrowed at runtime in `src/lib/api/transcript.ts`, with a comment
explaining why. Adding response models to the simulator would fix this
properly, but that package was out of scope for this change.

## Known limitations

- **Agent runs watch the firehose, not a filtered stream.** The raw path sends
  its own `X-Request-Id` so it can be followed precisely. The agent simulator
  does not forward such a header to the gateway, so agent-driven runs subscribe
  to `/ws/live`. Fine for a single-tenant demo; it would need the simulator to
  propagate a correlation id to be correct with concurrent users.
- **The agent list is the demo delegation.** The gateway has no "list agents"
  endpoint, so `/agents` reads the control-plane endpoints that do exist rather
  than inventing a roster.
- **Rego highlighting is hand-rolled** (`src/lib/rego-highlight.tsx`) — a small
  tokenizer for keywords, strings, comments, numbers and builtins, rather than
  a highlighting library.
- There is no other UI. The Streamlit dashboard that used to run at `:8501`
  has been removed entirely — this app is the only frontend.
