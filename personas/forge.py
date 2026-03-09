"""Forge persona -- Tier 2 code generator with Iron Gate enforcement."""

from __future__ import annotations

import re
from typing import Any, Optional

from core import router
from personas.base import Persona

# Regex to strip markdown code fences from LLM output
_CODE_FENCE_RE = re.compile(r"^```[a-zA-Z]*\n?|```\s*$", re.MULTILINE)


def _strip_fences(text: str) -> str:
    """Remove markdown code fences (``` ... ```) from a string."""
    return _CODE_FENCE_RE.sub("", text).strip()


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

    # ── New skill methods ────────────────────────────────────────────

    def refactor(self, code: str, goal: Optional[str] = None) -> str:
        """Refactor code for readability, performance, or a specific goal.

        Args:
            code: Source code to refactor.
            goal: Optional specific refactoring goal (e.g. 'performance').

        Returns:
            Refactored code string.
        """
        goal_clause = f" Focus especially on: {goal}." if goal else ""
        system = (
            "You are Forge, a refactoring specialist. Refactor the provided code "
            "while strictly preserving its external behavior. Improve variable and "
            "function naming for clarity, reduce code duplication, and apply SOLID "
            "principles where appropriate. Prefer small, focused functions.{goal}"
            "\n\nReturn only the refactored code, no markdown fences or explanation."
        ).format(goal=goal_clause)

        response = router.route(
            self.name,
            code,
            system_prompt=system,
        )
        response = _strip_fences(response)
        self.iron_gate_check(response)
        return response

    def add_tests(self, code: str, framework: str = "pytest") -> str:
        """Generate unit tests for the given code.

        Args:
            code: Source code to generate tests for.
            framework: Testing framework to use (default: 'pytest').

        Returns:
            Generated test code string.
        """
        system = (
            "You are Forge, a test-generation specialist. Write comprehensive unit "
            "tests for the provided code using the {framework} framework. "
            "Cover edge cases including empty inputs, boundary values, and error "
            "paths. Use parametrize where multiple similar cases exist. Mock "
            "external dependencies (network, filesystem, databases) instead of "
            "calling them. Each test should have a clear, descriptive name."
            "\n\nReturn only the test code, no markdown fences or explanation."
        ).format(framework=framework)

        response = router.route(
            self.name,
            code,
            system_prompt=system,
        )
        response = _strip_fences(response)
        self.iron_gate_check(response)
        return response

    def convert_language(self, code: str, target_language: str) -> str:
        """Convert code from one programming language to another idiomatically.

        Args:
            code: Source code to convert.
            target_language: Target language (e.g. 'rust', 'go', 'typescript').

        Returns:
            Converted code string in the target language.
        """
        system = (
            "You are Forge, a polyglot code translator. Convert the provided code "
            "into idiomatic {lang}. Do not merely transliterate syntax; use "
            "{lang}'s native idioms, standard library, error-handling conventions, "
            "and naming style. Preserve the original logic and behavior."
            "\n\nReturn only the converted code, no markdown fences or explanation."
        ).format(lang=target_language)

        response = router.route(
            self.name,
            code,
            system_prompt=system,
        )
        response = _strip_fences(response)
        self.iron_gate_check(response)
        return response

    def document(self, code: str) -> str:
        """Generate comprehensive docstrings and comments for code.

        Args:
            code: Source code to document.

        Returns:
            The same code with added documentation.
        """
        system = (
            "You are Forge, a documentation specialist. Add thorough documentation "
            "to the provided code. Include a module-level docstring summarizing the "
            "file's purpose. Add docstrings to every function and class describing "
            "parameters, return values, and raised exceptions. Add inline comments "
            "only for genuinely complex or non-obvious logic -- do not comment the "
            "obvious. Preserve all existing code exactly; only add documentation."
            "\n\nReturn only the documented code, no markdown fences or explanation."
        )

        response = router.route(
            self.name,
            code,
            system_prompt=system,
        )
        response = _strip_fences(response)
        self.iron_gate_check(response)
        return response
