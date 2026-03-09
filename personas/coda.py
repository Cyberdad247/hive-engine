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


@dataclass
class ChangelogResult:
    """Structured changelog generated from a diff or list of changes."""
    version: str
    date: str
    sections: dict[str, list[str]] = field(default_factory=lambda: {
        "added": [], "changed": [], "fixed": [],
        "removed": [], "security": [],
    })
    summary: str = ""


@dataclass
class DiffSummaryResult:
    """Human-readable summary of a code diff."""
    summary: str
    files_changed: list[dict[str, str]] = field(default_factory=list)
    impact: str = "low"
    breaking_changes: list[str] = field(default_factory=list)


@dataclass
class MeetingNotesResult:
    """Structured meeting notes extracted from a transcript."""
    title: str = ""
    attendees: list[str] = field(default_factory=list)
    key_points: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    action_items: list[dict[str, str]] = field(default_factory=list)
    follow_ups: list[str] = field(default_factory=list)


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

    # ------------------------------------------------------------------
    # Changelog generation
    # ------------------------------------------------------------------

    _changelog_system_prompt = (
        "You are Coda, the changelog generator. Given a git diff or list of "
        "changes, produce a structured changelog following the Keep a Changelog "
        "format (https://keepachangelog.com). Categorize every change accurately "
        "into one of: added, changed, fixed, removed, security. Write concise, "
        "user-facing descriptions (not developer jargon). Infer an appropriate "
        "semantic version bump and provide today's date in YYYY-MM-DD format.\n\n"
        "Return a JSON object with:\n"
        "- version: string (semantic version, e.g. '1.2.0')\n"
        "- date: string (YYYY-MM-DD)\n"
        "- sections: object with keys 'added', 'changed', 'fixed', 'removed', "
        "'security', each mapping to a list of strings\n"
        "- summary: a one-sentence overall summary of this release\n\n"
        "Output valid JSON only. No markdown fences."
    )

    def changelog(self, diff_text: str, **kwargs: Any) -> ChangelogResult:
        """Generate a structured changelog from a git diff or change list.

        Args:
            diff_text: A git diff, commit log, or free-form list of changes.

        Returns:
            ChangelogResult with version, date, categorized sections, and summary.
        """
        system = kwargs.pop("system_prompt", self._changelog_system_prompt)

        response = router.route(
            self.name,
            f"Generate a changelog from the following changes:\n\n{diff_text}",
            system_prompt=system,
            **kwargs,
        )

        self.iron_gate_check(response)

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

        default_sections = {
            "added": [], "changed": [], "fixed": [],
            "removed": [], "security": [],
        }
        raw_sections = data.get("sections", {})
        for key in default_sections:
            default_sections[key] = raw_sections.get(key, [])

        return ChangelogResult(
            version=data.get("version", "0.0.0"),
            date=data.get("date", ""),
            sections=default_sections,
            summary=data.get("summary", ""),
        )

    # ------------------------------------------------------------------
    # Diff summary
    # ------------------------------------------------------------------

    _diff_summary_system_prompt = (
        "You are Coda, the diff analysis engine. Given a code diff, produce a "
        "concise human-readable summary. Focus on the *intent* behind the "
        "changes, not just what lines were added or removed. Flag any breaking "
        "changes explicitly. Assess the overall impact as 'low', 'medium', or "
        "'high' based on scope and risk.\n\n"
        "Return a JSON object with:\n"
        "- summary: a short paragraph describing the overall change\n"
        "- files_changed: list of objects, each with 'file' (path) and "
        "'changes' (brief description)\n"
        "- impact: one of 'low', 'medium', 'high'\n"
        "- breaking_changes: list of strings (empty if none)\n\n"
        "Output valid JSON only. No markdown fences."
    )

    def diff_summary(self, diff_text: str, **kwargs: Any) -> DiffSummaryResult:
        """Summarize a code diff into a concise human-readable description.

        Args:
            diff_text: A unified diff (e.g. output of ``git diff``).

        Returns:
            DiffSummaryResult with summary, per-file changes, impact, and
            any breaking changes.
        """
        system = kwargs.pop("system_prompt", self._diff_summary_system_prompt)

        response = router.route(
            self.name,
            f"Summarize the following diff:\n\n{diff_text}",
            system_prompt=system,
            **kwargs,
        )

        self.iron_gate_check(response)

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

        impact = data.get("impact", "low")
        if impact not in ("low", "medium", "high"):
            impact = "low"

        return DiffSummaryResult(
            summary=data.get("summary", response[:200]),
            files_changed=data.get("files_changed", []),
            impact=impact,
            breaking_changes=data.get("breaking_changes", []),
        )

    # ------------------------------------------------------------------
    # Meeting notes
    # ------------------------------------------------------------------

    _meeting_notes_system_prompt = (
        "You are Coda, the meeting notes extractor. Given a meeting transcript "
        "or discussion, produce structured notes. Extract concrete decisions and "
        "action items. Identify owners for each action item when possible. Be "
        "concise -- prefer bullet points over prose.\n\n"
        "Return a JSON object with:\n"
        "- title: short descriptive title for the meeting\n"
        "- attendees: list of participant names mentioned\n"
        "- key_points: list of important topics or points discussed\n"
        "- decisions: list of decisions that were made\n"
        "- action_items: list of objects with 'owner', 'task', and 'deadline' "
        "(use 'TBD' for unknown deadlines, 'unassigned' for unknown owners)\n"
        "- follow_ups: list of items that need follow-up but aren't actionable yet\n\n"
        "Output valid JSON only. No markdown fences."
    )

    def meeting_notes(self, transcript: str, **kwargs: Any) -> MeetingNotesResult:
        """Convert a meeting transcript into structured notes.

        Args:
            transcript: Raw meeting transcript or discussion text.

        Returns:
            MeetingNotesResult with title, attendees, key points, decisions,
            action items, and follow-ups.
        """
        system = kwargs.pop("system_prompt", self._meeting_notes_system_prompt)

        response = router.route(
            self.name,
            f"Extract meeting notes from the following transcript:\n\n{transcript}",
            system_prompt=system,
            **kwargs,
        )

        self.iron_gate_check(response)

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

        return MeetingNotesResult(
            title=data.get("title", "Untitled Meeting"),
            attendees=data.get("attendees", []),
            key_points=data.get("key_points", []),
            decisions=data.get("decisions", []),
            action_items=data.get("action_items", []),
            follow_ups=data.get("follow_ups", []),
        )
