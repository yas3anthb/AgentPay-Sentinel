from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Never inherit the developer's .env — tests must be hermetic.
os.environ["AGENTPAY_ENV_FILE"] = str(ROOT / "tests" / ".env.absent")

# Tests never touch a real Postgres, Redis, OPA, or the OpenAI API.
os.environ.setdefault("ALLOW_DEGRADED_CLASSIFIER", "false")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "memory://")
os.environ.setdefault("CLASSIFIER_OFFLINE", "true")
os.environ.setdefault("JWT_PUBLIC_KEY_PATH", str(ROOT / "keys/delegation_public.pem"))
os.environ.setdefault("JWT_PRIVATE_KEY_PATH", str(ROOT / "keys/delegation_private.pem"))
os.environ.setdefault(
    "PAYMENT_SIGNING_PUBLIC_KEY_PATH", str(ROOT / "keys/payment_public.pem")
)
os.environ.setdefault(
    "PAYMENT_SIGNING_PRIVATE_KEY_PATH", str(ROOT / "keys/payment_private.pem")
)
os.environ.setdefault("DELEGATION_PRIVATE_KEY_PATH", str(ROOT / "keys/delegation_private.pem"))
os.environ.setdefault("DELEGATION_PUBLIC_KEY_PATH", str(ROOT / "keys/delegation_public.pem"))
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key")

# The edge rate limiter is exercised directly by tests/test_ratelimit.py. Every
# other test fires many intents for one agent inside a few seconds, so raise the
# ceilings out of the way here; the dedicated test lowers them explicitly.
os.environ.setdefault("EDGE_RATE_LIMIT_AGENT_PER_MIN", "1000000")
os.environ.setdefault("EDGE_RATE_LIMIT_DELEGATION_PER_MIN", "1000000")
