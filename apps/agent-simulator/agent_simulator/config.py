"""Agent-simulator configuration.

Deliberately separate from the gateway's settings. The simulator is an
*untrusted client* of Sentinel — it holds a delegation token and nothing else,
and it must not be able to reach into the gateway's configuration.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


@dataclass(frozen=True, slots=True)
class Settings:
    # --- where Sentinel lives ---
    gateway_url: str = "http://localhost:8080"
    provider_url: str = "http://localhost:9100"
    gateway_timeout_seconds: float = 45.0

    # --- who this agent is ---
    user_id: str = "user_ada"
    agent_id: str = "agent_shopper_01"
    delegation_id: str = "del_office_supplies"

    # --- the crew's LLM ---
    # A separate key from the gateway's classifier by default. They may share a
    # value, but they are configured independently so a key problem in one is
    # never silently absorbed by the other.
    agent_openai_api_key: str = ""
    agent_model: str = "gpt-4o-mini"
    agent_temperature: float = 0.0
    agent_timeout_seconds: float = 60.0
    agent_max_iterations: int = 6

    # "live"    -> real LLM calls; missing key is a hard error
    # "offline" -> deterministic stub, every transcript step marked simulated
    llm_mode: str = "live"

    crew_verbose: bool = False

    def offline(self) -> bool:
        return self.llm_mode.strip().lower() == "offline"


@lru_cache
def get_settings() -> Settings:
    return Settings(
        gateway_url=os.getenv("GATEWAY_URL", "http://localhost:8080"),
        provider_url=os.getenv("PROVIDER_URL", "http://localhost:9100"),
        gateway_timeout_seconds=float(os.getenv("GATEWAY_TIMEOUT_SECONDS", "45")),
        user_id=os.getenv("DEMO_USER_ID", "user_ada"),
        agent_id=os.getenv("DEMO_AGENT_ID", "agent_shopper_01"),
        delegation_id=os.getenv("DEMO_DELEGATION_ID", "del_office_supplies"),
        agent_openai_api_key=(
            os.getenv("AGENT_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        ),
        agent_model=os.getenv("AGENT_MODEL", "gpt-4o-mini"),
        agent_temperature=float(os.getenv("AGENT_TEMPERATURE", "0")),
        agent_timeout_seconds=float(os.getenv("AGENT_TIMEOUT_SECONDS", "60")),
        agent_max_iterations=int(os.getenv("AGENT_MAX_ITERATIONS", "6")),
        llm_mode=os.getenv("AGENT_LLM_MODE", "live"),
        crew_verbose=os.getenv("CREW_VERBOSE", "false").lower() == "true",
    )


class SimulatorError(Exception):
    """Anything that stops a simulation. Surfaced to the caller verbatim — the
    simulator never substitutes a plausible-looking transcript for a failure."""

    def __init__(self, code: str, message: str, detail: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}
