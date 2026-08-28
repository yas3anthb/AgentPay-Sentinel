"""LLM wiring for the crew.

Deliberately its own client, configured independently of the gateway's
classifier. They may share an API key value, but nothing is shared at runtime:
the gateway runs in a different process with its own OpenAI client, so a key
problem on one side surfaces on that side rather than being absorbed silently
by the other.

Fail closed: in live mode a missing key is a hard error. The simulator never
substitutes a plausible transcript for a failed LLM call.
"""
from __future__ import annotations

import logging

from .config import Settings, SimulatorError

log = logging.getLogger("agent_simulator.llm")


def build_crew_llm(settings: Settings):
    """Return a CrewAI LLM for the shopper/reviewer agents."""
    if settings.offline():
        raise SimulatorError(
            "LLM_NOT_AVAILABLE_OFFLINE",
            "offline mode does not build an LLM; the deterministic path is used instead",
        )

    if not settings.agent_openai_api_key:
        raise SimulatorError(
            "AGENT_LLM_KEY_MISSING",
            (
                "No AGENT_OPENAI_API_KEY (or OPENAI_API_KEY) is set, so the crew "
                "cannot run. This is a hard error on purpose: the simulator will "
                "not return an invented transcript. Set a key, or run with "
                "AGENT_LLM_MODE=offline for the clearly-labelled deterministic path."
            ),
        )

    from crewai import LLM

    return LLM(
        model=settings.agent_model,
        api_key=settings.agent_openai_api_key,
        temperature=settings.agent_temperature,
        timeout=settings.agent_timeout_seconds,
    )


def wrap_llm_errors(exc: Exception) -> SimulatorError:
    """Turn any crew/LLM failure into an explicit simulator error."""
    return SimulatorError(
        "AGENT_LLM_FAILED",
        f"The agent's LLM call failed ({type(exc).__name__}): {exc}. "
        "No transcript is returned for a run that did not happen.",
        {"exception_type": type(exc).__name__},
    )
