"""Auto-pipeline orchestration for HIVE Engine."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from core import router

logger = logging.getLogger("hive.pipeline")


@dataclass
class PipelineResult:
    """Result of a full pipeline run."""
    plan: str
    code: str
    security_review: str
    red_team_review: str
    success: bool = True
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class Pipeline:
    """Chains Oracle -> Forge -> (Sentinel + Aegis in parallel)."""

    def __init__(self) -> None:
        self._oracle_prompt = (
            "You are Oracle, the RPI planner. Given a task description, produce a "
            "structured JSON plan with steps, dependencies, and constraints. "
            "Output valid JSON only."
        )
        self._forge_prompt = (
            "You are Forge, the code generator. Given a plan, produce clean, "
            "well-structured Python code that implements it. Output the code only, "
            "no markdown fences."
        )
        self._sentinel_prompt = (
            "You are Sentinel, the security reviewer. Analyze the following code "
            "for security vulnerabilities. Return a JSON object with: "
            "findings (list of {issue, severity, line_hint}), overall_risk (low/medium/high)."
        )
        self._aegis_prompt = (
            "You are Aegis, the red team reviewer. Analyze the following code for "
            "attack vectors, edge cases, and failure modes. Return a JSON object with: "
            "risk_score (0-100), findings (list of strings), verdict (SHIP/HOLD/REDESIGN)."
        )

    async def run(self, task: str) -> PipelineResult:
        """Execute the full pipeline for a given task description."""
        errors: list[str] = []

        # Step 1: Oracle plans
        logger.info("Pipeline: Oracle planning...")
        try:
            plan = await asyncio.to_thread(
                router.route, "oracle", task, system_prompt=self._oracle_prompt
            )
        except Exception as e:
            logger.error("Oracle failed: %s", e)
            return PipelineResult(
                plan="", code="", security_review="", red_team_review="",
                success=False, errors=[f"Oracle failed: {e}"],
            )

        # Step 2: Forge generates code from the plan
        logger.info("Pipeline: Forge generating code...")
        forge_input = f"Plan:\n{plan}\n\nOriginal task:\n{task}"
        try:
            code = await asyncio.to_thread(
                router.route, "forge", forge_input, system_prompt=self._forge_prompt
            )
        except Exception as e:
            logger.error("Forge failed: %s", e)
            return PipelineResult(
                plan=plan, code="", security_review="", red_team_review="",
                success=False, errors=[f"Forge failed: {e}"],
            )

        # Step 3: Sentinel and Aegis review in parallel
        logger.info("Pipeline: Sentinel + Aegis reviewing in parallel...")

        async def _sentinel_review() -> str:
            try:
                return await asyncio.to_thread(
                    router.route, "sentinel", code, system_prompt=self._sentinel_prompt
                )
            except Exception as e:
                errors.append(f"Sentinel failed: {e}")
                return f'{{"error": "{e}"}}'

        async def _aegis_review() -> str:
            try:
                return await asyncio.to_thread(
                    router.route, "aegis", code, system_prompt=self._aegis_prompt
                )
            except Exception as e:
                errors.append(f"Aegis failed: {e}")
                return f'{{"error": "{e}"}}'

        security_review, red_team_review = await asyncio.gather(
            _sentinel_review(), _aegis_review()
        )

        logger.info("Pipeline complete.")
        return PipelineResult(
            plan=plan,
            code=code,
            security_review=security_review,
            red_team_review=red_team_review,
            success=len(errors) == 0,
            errors=errors,
        )
