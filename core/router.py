"""LiteLLM model routing for HIVE Engine personas."""

import os
import logging
from typing import Any

import litellm

logger = logging.getLogger("hive.router")

# Model ladder: tier -> default model string
MODEL_LADDER: dict[int, str] = {
    1: "anthropic/claude-3-5-haiku-20241022",
    2: "anthropic/claude-sonnet-4-20250514",
    3: "anthropic/claude-opus-4-20250514",
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


def _resolve_model(persona_name: str) -> str:
    """Resolve the model string for a persona, respecting HIVE_MODEL env override."""
    override = os.environ.get("HIVE_MODEL")
    if override:
        logger.debug("Using HIVE_MODEL override: %s", override)
        return override
    tier = TIER_MAP.get(persona_name.lower(), 2)
    model = MODEL_LADDER[tier]
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
    response = litellm.completion(**call_kwargs)
    content = response.choices[0].message.content
    return content or ""
