# The control plane

A separate service (`control_plane/`, port **8090**). It owns the registry the
gateway reads from and it is the only component that can mint a delegation
token. The enforcement gateway can do none of this and is not given the key to.

## Why it is separate

| | Control plane | Gateway |
|---|---|---|
| Registers agents / policies / merchants | ✅ | ✗ |
| Revokes / reinstates delegations | ✅ | ✗ |
| **Mints delegation tokens** | ✅ (holds delegation *private* key) | ✗ |
| Verifies inbound delegation JWTs | ✗ | ✅ (delegation *public* key only) |
| Issues scoped payment / approval tokens | ✗ | ✅ (its own *payment* keypair) |
| Can authorize a payment | ✗ | ✅ |
| Auth | `X-Admin-Key` on every mutation | delegation JWT per request |

Two signing domains, two keypairs (`scripts/gen_keys.py` makes both):

- **delegation** — control plane signs, gateway verifies. In Compose the gateway
  mounts a volume that does not contain `delegation_private.pem` at all.
- **payment** — gateway signs its single-use payment tokens, the mock provider
  verifies.

## Auth

Every mutating call needs `X-Admin-Key: <ADMIN_API_KEY>`. Missing or wrong → 401,
no database access. `X-Admin-Id: <who>` is recorded (not trusted for authz) so
actions are attributable. A blank `ADMIN_API_KEY` makes the service refuse to
start outside dev/test.

It is a shared secret on purpose-for-the-demo. A real deployment puts SSO / mTLS
and per-operator identity here.

## Endpoints (all under `/v1/admin`, all authenticated)

| Method | Path | |
|---|---|---|
| PUT | `/agents` | upsert an agent registration |
| PUT | `/policies` | bind a spending policy to a delegation |
| PUT | `/merchants` | upsert a merchant registry entry |
| GET | `/policies/{delegation_id}` | read a bound policy |
| GET | `/merchants` | list merchants |
| POST | `/delegations/{id}/revoke` · `/reinstate` | near-real-time revocation |
| GET | `/delegations/revoked` | the current revocation set |
| POST | `/tokens` | **mint a delegation token** |
| GET | `/audit/admin` | the per-admin audit trail |
| POST | `/dev/reset` | DEV ONLY — clear transactions, chain, replay caches |

## Admin audit trail

Every mutation writes one row to `admin_audit_events`: `admin_id`, `action`,
`target`, a SHA-256 digest of the payload (never the payload itself, and never a
minted token), and a timestamp. Append-only. Read it with `GET /v1/admin/audit/admin`.

## Calling it

- **Demo scripts / agent simulator** — `CONTROL_PLANE_URL` + `ADMIN_API_KEY`
  env; the helpers attach the header.
- **Web** — the browser calls the same-origin `/api/control/*` proxy route,
  which injects `X-Admin-Key` from the server's environment. The key is never in
  a page bundle.
- **Tests** — `tests/test_control_plane.py` drives it directly;
  `tests/test_pipeline.py` seeds through it with a test admin key.
