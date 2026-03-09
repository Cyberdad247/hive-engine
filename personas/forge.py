"""Forge persona -- Tier 2 code generator with Iron Gate enforcement."""

from __future__ import annotations

from typing import Any

from core import router
from personas.base import Persona


class Forge(Persona):
    """Code generation persona. Every output passes Iron Gate before returning."""

    name = "forge"
    model_tier = 2
    allowed_tools = {"write_file", "read_file", "execute"}
    system_prompt = (
        "You are Forge, the HIVE Engine code generator. You write clean, "
        "well-structured, production-ready code. Follow best practices:\n"
        "- Type hints on all functions\n"
        "- Docstrings on public interfaces\n"
        "- Error handling with specific exceptions\n"
        "- No hardcoded secrets or credentials\n"
        "- Security-conscious patterns\n\n"
        "Output code only, no markdown fences unless asked."
    )

    def process(self, prompt: str, **kwargs: Any) -> str:
        """Generate code from a prompt.

        The output is always checked by Iron Gate before returning.
        Raises SecurityError if the generated code contains secrets.
        """
        system = kwargs.pop("system_prompt", self.system_prompt)
        extra_context = kwargs.pop("context", "")
        if extra_context:
            full_prompt = f"{extra_context}\n\n{prompt}"
        else:
            full_prompt = prompt

        response = router.route(
            self.name,
            full_prompt,
            system_prompt=system,
            **kwargs,
        )

        # Iron Gate: check for secrets before returning
        self.iron_gate_check(response)
        return response
