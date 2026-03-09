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

    # ------------------------------------------------------------------
    # JSON parsing helper (shared by the new skill methods)
    # ------------------------------------------------------------------

    def _parse_json_response(self, response: str, fallback: dict[str, Any]) -> dict[str, Any] | str:
        """Attempt to parse a JSON dict from *response*, falling back gracefully."""
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(response[start:end])
                except json.JSONDecodeError:
                    pass
            return {**fallback, "_raw": response}

    # ------------------------------------------------------------------
    # Skill: dependency_analysis
    # ------------------------------------------------------------------

    _DEPENDENCY_ANALYSIS_PROMPT = (
        "You are Oracle, the HIVE Engine dependency analyst. "
        "Given source code or a project description, perform a thorough "
        "dependency analysis:\n"
        "1. Identify every import / require / dependency declaration.\n"
        "2. Classify each as runtime, dev, or transitive.\n"
        "3. Flag outdated, deprecated, or risky dependencies (use risk "
        "levels: low, medium, high) and explain why.\n"
        "4. Detect any circular-dependency risks between modules.\n"
        "5. Provide actionable recommendations.\n\n"
        "Return valid JSON only (no markdown fences) with this schema:\n"
        '{"dependencies": [{"name": str, "type": "runtime"|"dev"|"transitive", '
        '"risk": "low"|"medium"|"high", "notes": str}], '
        '"circular_risks": [str], "recommendations": [str]}'
    )

    def dependency_analysis(self, code_or_description: str, **kwargs: Any) -> dict[str, Any]:
        """Analyze dependencies in a project or code snippet.

        Returns a dict with keys: dependencies, circular_risks, recommendations.
        """
        system = kwargs.pop("system_prompt", self._DEPENDENCY_ANALYSIS_PROMPT)
        response = router.route(
            self.name,
            code_or_description,
            system_prompt=system,
            **kwargs,
        )
        self.iron_gate_check(response)

        fallback: dict[str, Any] = {
            "dependencies": [],
            "circular_risks": [],
            "recommendations": [],
        }
        return self._parse_json_response(response, fallback)

    # ------------------------------------------------------------------
    # Skill: architecture_diagram
    # ------------------------------------------------------------------

    _ARCHITECTURE_DIAGRAM_PROMPT = (
        "You are Oracle, the HIVE Engine architecture visualiser. "
        "Given a system or feature description, generate a clear ASCII "
        "architecture diagram.\n"
        "Guidelines:\n"
        "- Use box-drawing characters (e.g. ┌ ─ ┐ │ └ ┘ ├ ┤ ┬ ┴ ┼) for "
        "component boxes.\n"
        "- Show every major component as a labelled box.\n"
        "- Use arrows (──>, <──, <──>) to indicate data-flow direction.\n"
        "- Label each connection/arrow with a short description of what "
        "flows between the components.\n"
        "- Keep the diagram readable at 80 columns.\n\n"
        "Return the ASCII diagram as plain text. No JSON, no markdown fences."
    )

    def architecture_diagram(self, description: str, **kwargs: Any) -> str:
        """Generate an ASCII architecture diagram from a description.

        Returns a plain string containing the diagram.
        """
        system = kwargs.pop("system_prompt", self._ARCHITECTURE_DIAGRAM_PROMPT)
        response = router.route(
            self.name,
            description,
            system_prompt=system,
            **kwargs,
        )
        self.iron_gate_check(response)
        return response

    # ------------------------------------------------------------------
    # Skill: estimate_effort
    # ------------------------------------------------------------------

    _ESTIMATE_EFFORT_PROMPT = (
        "You are Oracle, the HIVE Engine effort estimator. "
        "Given a task description, estimate the implementation effort.\n"
        "1. Break the work into concrete subtasks.\n"
        "2. Estimate hours for each subtask (include implementation, "
        "testing, code-review, and deployment time).\n"
        "3. Assign an overall complexity: low, medium, or high.\n"
        "4. Flag risks for each subtask.\n"
        "5. State any assumptions you made.\n\n"
        "Return valid JSON only (no markdown fences) with this schema:\n"
        '{"complexity": "low"|"medium"|"high", '
        '"estimated_hours": {"min": int, "max": int}, '
        '"breakdown": [{"task": str, "hours": float, "risk": str}], '
        '"assumptions": [str]}'
    )

    def estimate_effort(self, task_description: str, **kwargs: Any) -> dict[str, Any]:
        """Estimate implementation effort for a task.

        Returns a dict with keys: complexity, estimated_hours, breakdown, assumptions.
        """
        system = kwargs.pop("system_prompt", self._ESTIMATE_EFFORT_PROMPT)
        response = router.route(
            self.name,
            task_description,
            system_prompt=system,
            **kwargs,
        )
        self.iron_gate_check(response)

        fallback: dict[str, Any] = {
            "complexity": "medium",
            "estimated_hours": {"min": 0, "max": 0},
            "breakdown": [],
            "assumptions": [],
        }
        return self._parse_json_response(response, fallback)
