"""Muse persona -- Tier 2 prompt optimizer."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

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

    # -- UI mockup generation ------------------------------------------------

    _UI_MOCKUP_SYSTEM_PROMPT = (
        "You are Muse, a UI wireframe artist. "
        "Given a description of a user interface, create a visual text-based "
        "wireframe using Unicode box-drawing characters "
        "(┌ ─ ┐ │ └ ─ ┘ ├ ┤ ┬ ┴ ┼). "
        "Show the full layout including buttons, text inputs, navigation bars, "
        "sidebars, content areas, and any other elements implied by the description. "
        "Label every element clearly inside or beside its box. "
        "Use placeholder text (e.g. [Search...], [Submit], [Logo]) where appropriate. "
        "Return ONLY the ASCII wireframe -- no explanations, no markdown fences."
    )

    def ui_mockup(self, description: str, **kwargs: Any) -> str:
        """Generate an ASCII/text UI mockup from a description.

        Args:
            description: Natural-language description of the desired UI.

        Returns:
            A string containing the text-based wireframe.
        """
        system = kwargs.pop("system_prompt", self._UI_MOCKUP_SYSTEM_PROMPT)

        response = router.route(
            self.name,
            f"Create a text-based UI mockup for:\n\n{description}",
            system_prompt=system,
            **kwargs,
        )

        self.iron_gate_check(response)
        return response

    # -- Naming suggestions --------------------------------------------------

    _NAMING_SYSTEM_PROMPT = (
        "You are Muse, a naming consultant for software projects. "
        "Given a description and a naming context (variable, function, class, "
        "project, or api_endpoint), suggest clear, idiomatic names. "
        "Follow the dominant conventions for the context: "
        "snake_case for variables/functions, PascalCase for classes, "
        "kebab-case for projects, /kebab-case paths for API endpoints. "
        "Be descriptive but concise. Avoid abbreviations unless universally understood. "
        "Return valid JSON (no markdown fences) with this exact shape:\n"
        '{"suggestions": [{"name": "<str>", "reasoning": "<str>", "style": "<str>"}], '
        '"best_pick": "<str>", "naming_convention": "<str>"}'
    )

    def naming_suggestions(
        self,
        description: str,
        context: Literal[
            "variable", "function", "class", "project", "api_endpoint"
        ] = "variable",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Suggest names for variables, functions, classes, projects, or API endpoints.

        Args:
            description: What the thing being named represents or does.
            context: The naming context -- one of variable, function, class,
                     project, or api_endpoint.

        Returns:
            A dict with keys ``suggestions``, ``best_pick``, and
            ``naming_convention``.
        """
        system = kwargs.pop("system_prompt", self._NAMING_SYSTEM_PROMPT)

        response = router.route(
            self.name,
            f"Suggest names for the following ({context}):\n\n{description}",
            system_prompt=system,
            **kwargs,
        )

        self.iron_gate_check(response)

        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(response[start:end])
                except json.JSONDecodeError:
                    data = {"suggestions": [], "best_pick": "", "naming_convention": ""}
            else:
                data = {"suggestions": [], "best_pick": "", "naming_convention": ""}

        return data

    # -- Brainstorm ----------------------------------------------------------

    _BRAINSTORM_SYSTEM_PROMPT = (
        "You are Muse, a creative brainstorming partner. "
        "Given a topic or problem, generate creative ideas and approaches. "
        "Think divergently: include both conventional best-practice approaches "
        "and unconventional or experimental ones. "
        "Honestly evaluate trade-offs for each idea -- list real pros and cons. "
        "Rate the implementation effort as low, medium, or high. "
        "Return valid JSON (no markdown fences) with this exact shape:\n"
        '{"ideas": [{"title": "<str>", "description": "<str>", '
        '"pros": ["<str>"], "cons": ["<str>"], '
        '"effort": "low"|"medium"|"high"}], '
        '"recommended": "<title of best idea>", "reasoning": "<str>"}'
    )

    def brainstorm(
        self,
        topic: str,
        num_ideas: int = 5,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate creative ideas and approaches for a given topic.

        Args:
            topic: The problem or topic to brainstorm about.
            num_ideas: How many ideas to generate (default 5).

        Returns:
            A dict with keys ``ideas``, ``recommended``, and ``reasoning``.
        """
        system = kwargs.pop("system_prompt", self._BRAINSTORM_SYSTEM_PROMPT)

        response = router.route(
            self.name,
            f"Brainstorm exactly {num_ideas} ideas for:\n\n{topic}",
            system_prompt=system,
            **kwargs,
        )

        self.iron_gate_check(response)

        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(response[start:end])
                except json.JSONDecodeError:
                    data = {"ideas": [], "recommended": "", "reasoning": ""}
            else:
                data = {"ideas": [], "recommended": "", "reasoning": ""}

        return data
