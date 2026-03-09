"""Apis persona -- Tier 2 browser automation."""

from __future__ import annotations

from typing import Any

from core import router
from personas.base import Persona


class Apis(Persona):
    """Browser automation persona. Generates Playwright test and crawl scripts."""

    name = "apis"
    model_tier = 2
    allowed_tools = {"read_file", "execute"}
    system_prompt = (
        "You are Apis, the HIVE Engine browser automation specialist. "
        "You generate Playwright (Python) scripts for testing and crawling.\n\n"
        "For test scripts: use pytest-playwright patterns with proper assertions.\n"
        "For crawl scripts: use async Playwright with proper error handling.\n\n"
        "Always include:\n"
        "- Proper imports\n"
        "- Error handling and timeouts\n"
        "- Headless mode by default\n"
        "- Clean browser context management\n\n"
        "Output code only, no markdown fences."
    )

    _test_system = (
        "You are Apis generating a Playwright test script. Use pytest-playwright. "
        "Include proper page.goto(), assertions with expect(), and cleanup. "
        "Output complete runnable Python code only."
    )

    _crawl_system = (
        "You are Apis generating a Playwright crawl script. Use async Playwright. "
        "Include proper error handling, rate limiting, and data extraction. "
        "Output complete runnable Python code only."
    )

    def process(self, prompt: str, **kwargs: Any) -> str:
        """Generate a Playwright script for a given URL or task.

        Args:
            prompt: URL or description of what to test/crawl.
            **kwargs: mode='test' or mode='crawl' (default: 'test').

        Returns:
            Generated Playwright script as a string.
        """
        mode = kwargs.pop("mode", "test")
        if mode == "crawl":
            system = self._crawl_system
        else:
            system = self._test_system

        system = kwargs.pop("system_prompt", system)

        response = router.route(
            self.name,
            f"Target: {prompt}\nMode: {mode}",
            system_prompt=system,
            **kwargs,
        )

        self.iron_gate_check(response)

        # Strip markdown fences if present
        lines = response.strip().splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        return "\n".join(lines)

    def generate_test(self, url: str, **kwargs: Any) -> str:
        """Convenience method for generating a test script."""
        return self.process(url, mode="test", **kwargs)

    def generate_crawl(self, url: str, **kwargs: Any) -> str:
        """Convenience method for generating a crawl script."""
        return self.process(url, mode="crawl", **kwargs)
