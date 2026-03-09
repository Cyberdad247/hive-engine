"""LiteLLM model routing for HIVE Engine personas."""

import os
import logging
from typing import Any

import litellm

logger = logging.getLogger("hive.router")

# ─── Model Ladders ───────────────────────────────────────────────
# Switch between providers by setting HIVE_PROVIDER env var.
# Supported: "gemini" (default), "openai", "anthropic", "ollama"

LADDERS: dict[str, dict[int, str]] = {
    "gemini": {
        1: "gemini/gemini-2.5-flash",                # Light: Sentinel, Coda (stable)
        2: "gemini/gemini-2.5-flash",                # Standard: Forge, Oracle, Debug, Muse, Apis
        3: "gemini/gemini-2.5-flash",                # Heavy: Aegis
    },
    "gemini-3.1": {
        1: "gemini/gemini-3.1-flash-lite-preview",   # Light: preview, may be unavailable
        2: "gemini/gemini-3.1-pro-preview",           # Standard: preview
        3: "gemini/gemini-3.1-pro-preview",           # Heavy: preview
    },
    "openai": {
        1: "gpt-4o-mini",        # Light: Sentinel, Coda
        2: "gpt-4o",             # Standard: Forge, Oracle, Debug, Muse, Apis
        3: "gpt-4o",             # Heavy: Aegis
    },
    "anthropic": {
        1: "anthropic/claude-haiku-4-5-20251001",
        2: "anthropic/claude-sonnet-4-6-20260320",
        3: "anthropic/claude-opus-4-6-20260320",
    },
    "ollama": {
        1: "ollama/qwen3.5:4b",  # All same model on <= 8GB RAM
        2: "ollama/qwen3.5:4b",
        3: "ollama/qwen3.5:4b",
    },
    "ollama-tiered": {
        1: "ollama/qwen3.5:2b",  # For 16GB+ RAM systems
        2: "ollama/qwen3.5:4b",
        3: "ollama/qwen3.5:9b",
    },
}

# Persona name -> tier mapping
TIER_MAP: dict[str, int] = {
    "sentinel": 1,
    "coda": 1,
    "forge": 2,
    "oracle": 2,
    "debug": 2,
    "muse": 2,
    "apis": 2,
    "aegis": 3,
}


def _get_ladder() -> dict[int, str]:
    """Get the active model ladder based on HIVE_PROVIDER env var."""
    provider = os.environ.get("HIVE_PROVIDER", "gemini").lower()
    if provider not in LADDERS:
        logger.warning("Unknown HIVE_PROVIDER '%s', falling back to openai", provider)
        provider = "openai"
    return LADDERS[provider]


def _resolve_model(persona_name: str) -> str:
    """Resolve the model string for a persona, respecting HIVE_MODEL env override."""
    override = os.environ.get("HIVE_MODEL")
    if override:
        logger.debug("Using HIVE_MODEL override: %s", override)
        return override
    ladder = _get_ladder()
    tier = TIER_MAP.get(persona_name.lower(), 2)
    model = ladder[tier]
    logger.debug("Resolved %s (tier %d) -> %s", persona_name, tier, model)
    return model


def route(persona_name: str, prompt: str, **kwargs: Any) -> str:
    """Route a prompt to the appropriate model tier via LiteLLM.

    Args:
        persona_name: Name of the persona making the request.
        prompt: The user/system prompt content.
        **kwargs: Extra kwargs forwarded to litellm.completion
            (e.g. system_prompt, temperature, max_tokens).

    Returns:
        The model's response text.
    """
    model = _resolve_model(persona_name)

    messages: list[dict[str, str]] = []
    system_prompt = kwargs.pop("system_prompt", None)
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    extra_messages = kwargs.pop("messages", None)
    if extra_messages:
        messages = extra_messages

    call_kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    # Forward supported litellm params
    for key in ("temperature", "max_tokens", "top_p", "stop", "stream"):
        if key in kwargs:
            call_kwargs[key] = kwargs[key]

    logger.info("Routing %s -> %s (%d messages)", persona_name, model, len(messages))
    try:
        response = litellm.completion(**call_kwargs)
    except (litellm.exceptions.ServiceUnavailableError, litellm.exceptions.RateLimitError) as e:
        # Fallback: if using a preview/unstable provider, retry with stable gemini
        provider = os.environ.get("HIVE_PROVIDER", "gemini").lower()
        if provider != "gemini" and "gemini" in LADDERS:
            tier = TIER_MAP.get(persona_name.lower(), 2)
            fallback_model = LADDERS["gemini"][tier]
            logger.warning("Model %s unavailable, falling back to %s", model, fallback_model)
            call_kwargs["model"] = fallback_model
            response = litellm.completion(**call_kwargs)
        else:
            raise
    content = response.choices[0].message.content
    return content or ""
