"""Debug persona -- Tier 2 auto-healing."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any

from core import router
from personas.base import Persona


@dataclass
class HealAttempt:
    """Record of a single heal attempt."""
    iteration: int
    error: str
    fix_description: str
    code: str


@dataclass
class HealResult:
    """Result of the auto-healing process."""
    success: bool
    attempts: list[HealAttempt] = field(default_factory=list)
    final_error: str | None = None
    final_code: str | None = None


class Debug(Persona):
    """Auto-healing persona. Runs code, catches errors, generates fixes, retries."""

    name = "debug"
    model_tier = 2
    allowed_tools = {"read_file", "write_file", "execute"}
    max_attempts: int = 3
    system_prompt = (
        "You are Debug, the HIVE Engine auto-healer. Given Python code and an error, "
        "diagnose the root cause and produce a corrected version of the full code. "
        "Output the complete fixed code only, no explanations or markdown fences. "
        "Preserve all existing functionality while fixing the error."
    )

    def process(self, prompt: str, **kwargs: Any) -> HealResult:
        """Attempt to run code and auto-heal errors.

        Args:
            prompt: The file path to run, or raw code to execute.
            **kwargs: Optional max_attempts override.

        Returns:
            HealResult with success status, attempts list, and final state.
        """
        max_attempts = kwargs.pop("max_attempts", self.max_attempts)
        code = self._read_code(prompt)
        attempts: list[HealAttempt] = []

        for iteration in range(1, max_attempts + 1):
            # Try to run the code
            success, output, error = self._execute_code(code)

            if success:
                return HealResult(
                    success=True,
                    attempts=attempts,
                    final_code=code,
                )

            # Generate a fix
            fix_prompt = (
                f"The following Python code produced an error.\n\n"
                f"Code:\n```python\n{code}\n```\n\n"
                f"Error output:\n```\n{error}\n```\n\n"
                f"Attempt {iteration}/{max_attempts}. "
                f"Produce the complete corrected code."
            )

            fixed_code = router.route(
                self.name,
                fix_prompt,
                system_prompt=self.system_prompt,
            )

            # Iron Gate check on the fix
            self.iron_gate_check(fixed_code)

            # Strip markdown fences if present
            fixed_code = self._strip_fences(fixed_code)

            attempts.append(HealAttempt(
                iteration=iteration,
                error=error,
                fix_description=f"Auto-fix attempt {iteration}",
                code=fixed_code,
            ))

            code = fixed_code

        # Final attempt to run
        success, output, error = self._execute_code(code)
        if success:
            return HealResult(success=True, attempts=attempts, final_code=code)

        return HealResult(
            success=False,
            attempts=attempts,
            final_error=error,
            final_code=code,
        )

    def _read_code(self, prompt: str) -> str:
        """If prompt is a file path, read it. Otherwise treat as raw code."""
        try:
            with open(prompt) as f:
                return f.read()
        except (FileNotFoundError, OSError, IsADirectoryError):
            return prompt

    def _execute_code(self, code: str) -> tuple[bool, str, str]:
        """Execute Python code in a subprocess.

        Returns (success, stdout, stderr).
        """
        try:
            result = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return True, result.stdout, ""
            return False, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return False, "", "Execution timed out after 30 seconds"
        except Exception as e:
            return False, "", str(e)

    @staticmethod
    def _strip_fences(code: str) -> str:
        """Remove markdown code fences if present."""
        lines = code.strip().splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines)

    @staticmethod
    def _parse_json_response(text: str) -> dict[str, Any]:
        """Extract and parse a JSON object from an LLM response string."""
        cleaned = text.strip()
        # Strip markdown fences wrapping JSON
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)
        return json.loads(cleaned)

    # ── New analysis methods ─────────────────────────────────────

    def profile_performance(self, code: str) -> dict[str, Any]:
        """Analyze code for performance bottlenecks without executing it.

        Args:
            code: Source code to analyze.

        Returns:
            Dict with bottlenecks, complexity estimates, and recommendations.
        """
        system_prompt = (
            "You are a performance analysis expert. Analyze the provided code for "
            "performance bottlenecks WITHOUT executing it. Examine algorithmic "
            "complexity (time and space), identify N+1 query patterns, unnecessary "
            "memory allocations, blocking I/O operations, and redundant computations. "
            "Suggest concrete optimizations for each issue found.\n\n"
            "Respond with ONLY a JSON object (no markdown fences, no explanation) "
            "matching this schema:\n"
            '{"bottlenecks": [{"location": "<function or line description>", '
            '"issue": "<description>", "severity": "low"|"medium"|"high", '
            '"suggestion": "<optimization>"}], '
            '"complexity": {"time": "<Big-O>", "space": "<Big-O>"}, '
            '"recommendations": ["<general recommendation>"]}'
        )

        prompt = f"Analyze the following code for performance issues:\n\n```\n{code}\n```"

        response = router.route(
            self.name,
            prompt,
            system_prompt=system_prompt,
        )
        return self._parse_json_response(response)

    def trace_error(self, error_message: str, code: str | None = None) -> dict[str, Any]:
        """Diagnose the root cause of an error message.

        Args:
            error_message: The error output or traceback to analyze.
            code: Optional source code for additional context.

        Returns:
            Dict with root cause, explanation, fix steps, optional code fix,
            and related errors.
        """
        system_prompt = (
            "You are an expert error diagnostician. Parse the provided traceback or "
            "error message and identify the TRUE root cause, not just the surface "
            "symptom. Explain why the error occurred, provide step-by-step fix "
            "instructions, and if source code is provided, supply a corrected code "
            "snippet. Also list related errors the user might encounter after fixing "
            "this one.\n\n"
            "Respond with ONLY a JSON object (no markdown fences, no explanation) "
            "matching this schema:\n"
            '{"root_cause": "<concise root cause>", '
            '"explanation": "<detailed explanation>", '
            '"fix_steps": ["<step 1>", "<step 2>"], '
            '"code_fix": "<corrected code snippet or null if no code provided>", '
            '"related_errors": ["<error that might surface next>"]}'
        )

        prompt = f"Error message:\n```\n{error_message}\n```"
        if code is not None:
            prompt += f"\n\nSource code:\n```\n{code}\n```"

        response = router.route(
            self.name,
            prompt,
            system_prompt=system_prompt,
        )
        return self._parse_json_response(response)

    def explain_stacktrace(self, stacktrace: str) -> dict[str, Any]:
        """Explain a raw stack trace in plain English.

        Args:
            stacktrace: The raw stack trace text.

        Returns:
            Dict with a summary, per-frame explanations, root cause, and
            suggested fix.
        """
        system_prompt = (
            "You are a friendly debugging assistant. Take the provided stack trace "
            "and explain it in plain English. For each frame, describe what the code "
            "was doing at that point. Identify which frame originated the error and "
            "why. Suggest a fix in simple, non-jargon terms.\n\n"
            "Respond with ONLY a JSON object (no markdown fences, no explanation) "
            "matching this schema:\n"
            '{"summary": "<one-sentence plain-English summary>", '
            '"frames": [{"file": "<file path>", "line": <line number>, '
            '"function": "<function name>", '
            '"explanation": "<what this frame was doing>"}], '
            '"root_cause": "<plain-English root cause>", '
            '"suggested_fix": "<plain-English fix>"}'
        )

        prompt = f"Explain this stack trace:\n\n```\n{stacktrace}\n```"

        response = router.route(
            self.name,
            prompt,
            system_prompt=system_prompt,
        )
        return self._parse_json_response(response)
