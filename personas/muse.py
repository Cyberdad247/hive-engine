"""Muse persona -- Tier 2 prompt optimizer."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from core import router
from personas.base import Persona


@dataclass
class PromptVariants:
    """Three optimized variants of an input prompt."""
    original: str
    precise: str     # Constrained, specific
    constrained: str  # Minimal, focused
    creative: str    # Expansive, exploratory


class Muse(Persona):
    """Prompt optimizer persona. No tool access -- pure LLM reasoning."""

    name = "muse"
    model_tier = 2
    allowed_tools: set[str] = set()
    system_prompt = (
        "You are Muse, the HIVE Engine prompt optimizer. "
        "Given a prompt, produce exactly 3 optimized variants as a JSON object:\n\n"
        "1. precise: Rewrite to be highly constrained and specific. "
        "Add explicit constraints, format requirements, and success criteria.\n\n"
        "2. constrained: Rewrite to be minimal and focused. "
        "Strip all ambiguity, reduce to essential instruction, add boundaries.\n\n"
        "3. creative: Rewrite to be expansive and exploratory. "
        "Encourage lateral thinking, open-ended exploration, novel approaches.\n\n"
        "Output valid JSON with keys: precise, constrained, creative. "
        "Each value is the rewritten prompt string. No markdown fences."
    )

    def process(self, prompt: str, **kwargs: Any) -> PromptVariants:
        """Optimize a prompt into three variants.

        Args:
            prompt: The original prompt to optimize.

        Returns:
            PromptVariants with precise, constrained, and creative versions.
        """
        system = kwargs.pop("system_prompt", self.system_prompt)

        response = router.route(
            self.name,
            f"Optimize this prompt:\n\n{prompt}",
            system_prompt=system,
            **kwargs,
        )

        self.iron_gate_check(response)

        # Parse JSON response
        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(response[start:end])
                except json.JSONDecodeError:
                    data = {}
            else:
                data = {}

        return PromptVariants(
            original=prompt,
            precise=data.get("precise", response),
            constrained=data.get("constrained", response),
            creative=data.get("creative", response),
        )
