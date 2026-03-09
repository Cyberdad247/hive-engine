"""Oracle persona -- Tier 2 RPI planner."""

from __future__ import annotations

import json
from typing import Any

from core import router
from personas.base import Persona


class Oracle(Persona):
    """RPI planner persona. Produces structured JSON task DAGs.

    Cannot write files -- read and search only.
    """

    name = "oracle"
    model_tier = 2
    allowed_tools = {"read_file", "search"}
    system_prompt = (
        "You are Oracle, the HIVE Engine architect and planner. "
        "Given a task, produce a structured JSON plan with:\n"
        "- steps: list of {id, action, description, persona, inputs, outputs}\n"
        "- dependencies: list of {from_step, to_step} edges\n"
        "- constraints: list of strings (security, performance, etc.)\n"
        "- estimated_complexity: low/medium/high\n\n"
        "Output valid JSON only. No markdown fences."
    )

    def process(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        """Plan a task and return a structured JSON DAG.

        Returns a dict with keys: steps, dependencies, constraints, estimated_complexity.
        If the LLM response isn't valid JSON, wraps it in a fallback structure.
        """
        system = kwargs.pop("system_prompt", self.system_prompt)
        context = kwargs.pop("context", "")
        full_prompt = f"{context}\n\n{prompt}" if context else prompt

        response = router.route(
            self.name,
            full_prompt,
            system_prompt=system,
            **kwargs,
        )

        # Iron Gate check (inherited)
        self.iron_gate_check(response)

        # Parse JSON response
        try:
            plan = json.loads(response)
        except json.JSONDecodeError:
            # Try to extract JSON from the response
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    plan = json.loads(response[start:end])
                except json.JSONDecodeError:
                    plan = {
                        "steps": [{"id": 1, "description": response}],
                        "dependencies": [],
                        "constraints": [],
                        "estimated_complexity": "medium",
                        "_raw": response,
                    }
            else:
                plan = {
                    "steps": [{"id": 1, "description": response}],
                    "dependencies": [],
                    "constraints": [],
                    "estimated_complexity": "medium",
                    "_raw": response,
                }

        return plan
