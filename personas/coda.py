"""Coda persona -- Tier 1 compression engine."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from core import router
from personas.base import Persona


@dataclass
class CompressedAnchor:
    """A compressed representation of a conversation or text."""
    summary: str
    key_decisions: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    assertions: list[str] = field(default_factory=list)


@dataclass
class VerificationResult:
    """Result of assertion verification."""
    valid: bool
    contradictions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class Coda(Persona):
    """Compression persona. Distills long text into structured anchors."""

    name = "coda"
    model_tier = 1
    allowed_tools = {"read_file"}
    system_prompt = (
        "You are Coda, the HIVE Engine compression engine. "
        "Given a long text (conversation, document, etc.), produce a compressed "
        "anchor as a JSON object with:\n"
        "- summary: 2-3 sentence summary of the core content\n"
        "- key_decisions: list of important decisions made\n"
        "- constraints: list of constraints or requirements identified\n"
        "- assertions: list of factual assertions that can be verified later\n\n"
        "Output valid JSON only. No markdown fences."
    )

    def process(self, prompt: str, **kwargs: Any) -> CompressedAnchor:
        """Compress long text into a structured anchor.

        Args:
            prompt: The text to compress.

        Returns:
            CompressedAnchor with summary, decisions, constraints, assertions.
        """
        system = kwargs.pop("system_prompt", self.system_prompt)

        response = router.route(
            self.name,
            f"Compress the following text:\n\n{prompt}",
            system_prompt=system,
            **kwargs,
        )

        self.iron_gate_check(response)

        # Parse JSON
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

        return CompressedAnchor(
            summary=data.get("summary", response[:200]),
            key_decisions=data.get("key_decisions", []),
            constraints=data.get("constraints", []),
            assertions=data.get("assertions", []),
        )

    def verify(self, session_id: str, anchors: list[CompressedAnchor] | None = None,
               **kwargs: Any) -> VerificationResult:
        """Check assertions across anchors for contradictions.

        Args:
            session_id: Session identifier for context.
            anchors: List of anchors to cross-check. If None, returns empty result.

        Returns:
            VerificationResult with contradictions and warnings.
        """
        if not anchors or len(anchors) < 2:
            return VerificationResult(valid=True)

        # Collect all assertions
        all_assertions: list[str] = []
        for anchor in anchors:
            all_assertions.extend(anchor.assertions)

        if not all_assertions:
            return VerificationResult(valid=True)

        # Ask LLM to find contradictions
        verify_prompt = (
            f"Session: {session_id}\n\n"
            f"Review these assertions for contradictions or inconsistencies:\n\n"
            + "\n".join(f"- {a}" for a in all_assertions)
            + "\n\nReturn a JSON object with:\n"
            "- valid: boolean (true if no contradictions)\n"
            "- contradictions: list of strings describing contradictions found\n"
            "- warnings: list of strings for potential issues\n"
            "Output JSON only."
        )

        response = router.route(
            self.name,
            verify_prompt,
            system_prompt=(
                "You are Coda, the verification engine. Check assertions for "
                "logical contradictions and inconsistencies. Be precise."
            ),
        )

        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(response[start:end])
                except json.JSONDecodeError:
                    data = {"valid": True}
            else:
                data = {"valid": True}

        return VerificationResult(
            valid=data.get("valid", True),
            contradictions=data.get("contradictions", []),
            warnings=data.get("warnings", []),
        )
