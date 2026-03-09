"""Base Persona class for HIVE Engine."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any


class SecurityError(Exception):
    """Raised when Iron Gate detects secrets in output."""

    def __init__(self, findings: list[str]) -> None:
        self.findings = findings
        super().__init__(f"Iron Gate blocked output: {'; '.join(findings)}")


# Patterns that Iron Gate scans for
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Anthropic API key", re.compile(r"sk-ant-[a-zA-Z0-9\-_]{20,}")),
    ("Stripe secret key", re.compile(r"sk_live_[a-zA-Z0-9]{20,}")),
    ("GitHub PAT", re.compile(r"ghp_[a-zA-Z0-9]{36,}")),
    ("GitHub OAuth", re.compile(r"gho_[a-zA-Z0-9]{36,}")),
    ("Generic secret key prefix", re.compile(r"sk-[a-zA-Z0-9]{20,}")),
    ("API key assignment", re.compile(r"""api_key\s*=\s*["'][^"']{8,}["']""")),
    ("Token assignment", re.compile(r"""token\s*=\s*["'][^"']{8,}["']""")),
    ("Secret assignment", re.compile(r"""secret\s*=\s*["'][^"']{8,}["']""")),
    ("Password assignment", re.compile(r"""password\s*=\s*["'][^"']{8,}["']""")),
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Private key block", re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----")),
]


class Persona(ABC):
    """Abstract base class for all HIVE personas.

    Attributes:
        name: Display name of the persona.
        system_prompt: The system prompt defining the persona's behavior.
        allowed_tools: Set of tool names this persona may use.
        model_tier: LiteLLM tier (1=haiku, 2=sonnet, 3=opus).
    """

    name: str = "base"
    system_prompt: str = "You are a helpful assistant."
    allowed_tools: set[str] = set()
    model_tier: int = 2

    def iron_gate_check(self, content: str) -> str:
        """Scan content for secret patterns. Raises SecurityError if found.

        Returns the content unchanged if no secrets are detected.
        """
        findings: list[str] = []
        for label, pattern in _SECRET_PATTERNS:
            matches = pattern.findall(content)
            if matches:
                # Redact the actual secret in the finding message
                for match in matches:
                    redacted = match[:6] + "..." + match[-4:] if len(match) > 10 else "***"
                    findings.append(f"{label}: {redacted}")
        if findings:
            raise SecurityError(findings)
        return content

    @abstractmethod
    def process(self, prompt: str, **kwargs: Any) -> Any:
        """Process a prompt and return the persona-specific result.

        Must be implemented by each persona subclass.
        """
        ...

    def can_use_tool(self, tool_name: str) -> bool:
        """Check if this persona is allowed to use a given tool."""
        return tool_name in self.allowed_tools

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} tier={self.model_tier}>"
