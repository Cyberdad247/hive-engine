"""Apis persona -- Tier 2 browser automation."""

from __future__ import annotations

from typing import Any, Dict

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

    _validate_contract_system = (
        "You are Apis validating an API specification for completeness and best "
        "practices. Analyse the provided API spec (OpenAPI/Swagger YAML/JSON or "
        "plain-text description) and return ONLY a valid JSON object with these keys:\n"
        '  "valid": bool,\n'
        '  "issues": [{"path": str, "severity": "error"|"warning"|"info", '
        '"message": str}],\n'
        '  "missing_endpoints": [str],\n'
        '  "recommendations": [str],\n'
        '  "score": int (0-100)\n\n'
        "Check for:\n"
        "- Missing error responses (4xx/5xx) on every endpoint\n"
        "- Inconsistent naming conventions (camelCase vs snake_case, plural vs "
        "singular resource names)\n"
        "- Missing authentication / authorization definitions\n"
        "- Missing pagination parameters on list endpoints\n"
        "- Missing rate-limiting documentation or headers\n"
        "- Missing request/response schemas or examples\n\n"
        "Output raw JSON only, no markdown fences."
    )

    _load_test_system = (
        "You are Apis generating a load/stress test script in Python. "
        "Generate a complete, runnable Python script using either locust or "
        "aiohttp (prefer aiohttp + asyncio for lightweight scenarios). "
        "The script MUST include:\n"
        "- Configurable concurrency (number of workers / virtual users)\n"
        "- Proper timing and duration controls\n"
        "- Result collection with min/max/avg/p95/p99 latency and error rate\n"
        "- A summary report printed at the end\n\n"
        "Scenario patterns:\n"
        '- "basic": steady constant load for a fixed duration\n'
        '- "spike": ramp from low to very high load suddenly, then back down\n'
        '- "endurance": moderate steady load over a long duration (30+ min)\n'
        '- "stress": incrementally increasing load until failure or timeout\n\n'
        "Output complete runnable Python code only, no markdown fences."
    )

    _mock_server_system = (
        "You are Apis generating a mock server implementation from an API "
        "description. Generate a complete, runnable Python mock server using "
        "FastAPI (preferred) or Flask. The server MUST include:\n"
        "- All endpoints described in the API spec with correct HTTP methods\n"
        "- Realistic sample/fixture data for every response\n"
        "- Proper HTTP status codes (200, 201, 204, 400, 404, 500 as appropriate)\n"
        "- Correct Content-Type and other relevant headers\n"
        "- Optional simulated delay (configurable via query param or env var)\n"
        "- A health-check endpoint at GET /health\n"
        "- CORS middleware enabled\n\n"
        "Output complete runnable Python code only, no markdown fences."
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

    # ------------------------------------------------------------------
    # New skills
    # ------------------------------------------------------------------

    def validate_contract(self, api_spec: str, **kwargs: Any) -> Dict[str, Any]:
        """Validate an API specification for completeness and best practices.

        Args:
            api_spec: OpenAPI/Swagger YAML/JSON or plain-text API description.
            **kwargs: Extra arguments forwarded to the router.

        Returns:
            A dict with keys: valid, issues, missing_endpoints,
            recommendations, score.
        """
        import json as _json

        response = router.route(
            self.name,
            f"API Specification to validate:\n{api_spec}",
            system_prompt=self._validate_contract_system,
            **kwargs,
        )

        self.iron_gate_check(response)

        # Strip markdown fences if present
        lines = response.strip().splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        raw = "\n".join(lines)

        try:
            return _json.loads(raw)
        except _json.JSONDecodeError:
            return {
                "valid": False,
                "issues": [
                    {
                        "path": "/",
                        "severity": "error",
                        "message": "LLM returned non-JSON; raw output attached.",
                    }
                ],
                "missing_endpoints": [],
                "recommendations": [raw],
                "score": 0,
            }

    def load_test(
        self, url: str, scenario: str = "basic", **kwargs: Any
    ) -> str:
        """Generate a load/stress test script for the given URL.

        Args:
            url: Target URL to load-test.
            scenario: One of "basic", "spike", "endurance", "stress".
            **kwargs: Extra arguments forwarded to the router.

        Returns:
            Runnable Python code as a string.
        """
        valid_scenarios = {"basic", "spike", "endurance", "stress"}
        if scenario not in valid_scenarios:
            raise ValueError(
                f"scenario must be one of {valid_scenarios!r}, got {scenario!r}"
            )

        response = router.route(
            self.name,
            f"Target URL: {url}\nScenario: {scenario}",
            system_prompt=self._load_test_system,
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

    def mock_server(self, api_spec: str, **kwargs: Any) -> str:
        """Generate a mock server implementation from an API description.

        Args:
            api_spec: OpenAPI/Swagger YAML/JSON or plain-text API description.
            **kwargs: Extra arguments forwarded to the router.

        Returns:
            Runnable Python code (FastAPI/Flask) as a string.
        """
        response = router.route(
            self.name,
            f"API Specification:\n{api_spec}",
            system_prompt=self._mock_server_system,
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
