"""Debug persona -- Tier 2 auto-healing."""

from __future__ import annotations

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
