"""Sentinel persona -- Tier 1 security reviewer."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from core import router
from personas.base import Persona


@dataclass
class SecurityFinding:
    """A single security finding."""
    issue: str
    severity: str  # low, medium, high, critical
    line_hint: str = ""
    recommendation: str = ""


@dataclass
class SecurityAssessment:
    """Complete security assessment result."""
    findings: list[SecurityFinding] = field(default_factory=list)
    overall_risk: str = "low"  # low, medium, high, critical
    summary: str = ""
    passed: bool = True


class Sentinel(Persona):
    """Security reviewer persona. Analyzes code for vulnerabilities.

    Read-only: cannot write files.
    """

    name = "sentinel"
    model_tier = 1
    allowed_tools = {"read_file"}
    system_prompt = (
        "You are Sentinel, the HIVE Engine security reviewer. "
        "Analyze code for security vulnerabilities. Return a JSON object with:\n"
        "- findings: list of {issue, severity, line_hint, recommendation}\n"
        "  severity is one of: low, medium, high, critical\n"
        "- overall_risk: low/medium/high/critical\n"
        "- summary: one-line summary\n"
        "- passed: boolean (true if no high/critical findings)\n\n"
        "Output valid JSON only. No markdown fences."
    )

    def process(self, prompt: str, **kwargs: Any) -> SecurityAssessment:
        """Analyze file content for security issues.

        Args:
            prompt: The file content or code to review.
            **kwargs: Extra args (e.g., file_path for context).

        Returns:
            SecurityAssessment with findings and overall risk.
        """
        file_path = kwargs.pop("file_path", None)
        system = kwargs.pop("system_prompt", self.system_prompt)

        review_prompt = prompt
        if file_path:
            review_prompt = f"File: {file_path}\n\n{prompt}"

        response = router.route(
            self.name,
            review_prompt,
            system_prompt=system,
            **kwargs,
        )

        self.iron_gate_check(response)

        # Parse the response into a SecurityAssessment
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

        findings = []
        for f in data.get("findings", []):
            if isinstance(f, dict):
                findings.append(SecurityFinding(
                    issue=f.get("issue", "Unknown"),
                    severity=f.get("severity", "medium"),
                    line_hint=f.get("line_hint", ""),
                    recommendation=f.get("recommendation", ""),
                ))

        overall_risk = data.get("overall_risk", "medium")
        passed = data.get("passed", not any(
            f.severity in ("high", "critical") for f in findings
        ))

        return SecurityAssessment(
            findings=findings,
            overall_risk=overall_risk,
            summary=data.get("summary", "Review complete."),
            passed=passed,
        )
