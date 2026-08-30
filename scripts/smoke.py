#!/usr/bin/env python3
"""Fast liveness check of the whole stack. Prints a green/red table and exits
non-zero if anything is down — enough to prove the demo is up in five seconds.
"""
from __future__ import annotations

import json
import os
import sys
import time

import httpx

G, R, Y, RST = "\033[32m", "\033[31m", "\033[33m", "\033[0m"

CHECKS = [
    ("web",           os.getenv("WEB_URL", "http://localhost:3000"),           "/",              None),
    ("gateway",       os.getenv("GATEWAY_URL", "http://localhost:8080"),       "/healthz",       "status"),
    ("gateway ready", os.getenv("GATEWAY_URL", "http://localhost:8080"),       "/readyz",        "ready"),
    ("control-plane", os.getenv("CONTROL_PLANE_URL", "http://localhost:8090"), "/healthz",       "status"),
    ("agent-sim",     os.getenv("SIMULATOR_URL", "http://localhost:9200"),     "/healthz",       "status"),
    ("agent ready",   os.getenv("SIMULATOR_URL", "http://localhost:9200"),     "/readyz",        "ready"),
    ("provider",      os.getenv("PROVIDER_URL", "http://localhost:9100"),      "/healthz",       "status"),
    ("event-relay",   os.getenv("RELAY_URL", "http://localhost:9300"),         "/healthz",       "status"),
]


def _probe(base: str, path: str, key: str | None) -> tuple[bool, str]:
    try:
        t0 = time.perf_counter()
        r = httpx.get(f"{base}{path}", timeout=5.0)
        ms = int((time.perf_counter() - t0) * 1000)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code} ({ms}ms)"
        if key is None:
            return True, f"200 ({ms}ms)"
        body = r.json()
        val = body.get(key)
        ok = val in (True, "ok")
        detail = f"{key}={val} ({ms}ms)"
        if key == "ready" and not ok:
            detail += f"  checks={json.dumps(body.get('checks', {}))}"
        return ok, detail
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def main() -> int:
    print(f"\n  {'service':<15} {'status':<6} detail")
    print("  " + "-" * 60)
    all_ok = True
    for name, base, path, key in CHECKS:
        ok, detail = _probe(base, path, key)
        all_ok &= ok
        mark = f"{G}UP{RST}" if ok else f"{R}DOWN{RST}"
        print(f"  {name:<15} {mark:<15} {detail}")
    print()
    if all_ok:
        print(f"  {G}all services up{RST}\n")
        return 0
    print(f"  {R}one or more services are down{RST} — try: docker compose up -d --build\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
