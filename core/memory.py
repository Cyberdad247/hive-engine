"""RAM-based tiered memory system for HIVE Engine."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Turn:
    """A single conversation turn."""
    role: str
    content: str
    persona: str
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompressedAnchor:
    """A compressed summary of a conversation segment."""
    summary: str
    key_decisions: list[str]
    constraints: list[str]
    assertions: list[str]
    turn_range: tuple[int, int]
    timestamp: float = field(default_factory=time.time)


class WorkingMemory:
    """Recent turns kept in a bounded deque (max 50)."""

    def __init__(self, max_turns: int = 50) -> None:
        self._turns: deque[Turn] = deque(maxlen=max_turns)
        self.max_turns = max_turns

    def add(self, turn: Turn) -> None:
        self._turns.append(turn)

    def get_recent(self, n: int | None = None) -> list[Turn]:
        if n is None:
            return list(self._turns)
        return list(self._turns)[-n:]

    def clear(self) -> None:
        self._turns.clear()

    @property
    def size(self) -> int:
        return len(self._turns)

    def to_messages(self, n: int | None = None) -> list[dict[str, str]]:
        """Convert recent turns to message dicts for LLM calls."""
        turns = self.get_recent(n)
        return [{"role": t.role, "content": t.content} for t in turns]


class CompressedMemory:
    """Stores Coda-generated compressed anchors."""

    def __init__(self) -> None:
        self._anchors: list[CompressedAnchor] = []

    def add(self, anchor: CompressedAnchor) -> None:
        self._anchors.append(anchor)

    def get_all(self) -> list[CompressedAnchor]:
        return list(self._anchors)

    def get_recent(self, n: int = 3) -> list[CompressedAnchor]:
        return self._anchors[-n:]

    def search(self, keyword: str) -> list[CompressedAnchor]:
        keyword_lower = keyword.lower()
        results = []
        for anchor in self._anchors:
            if keyword_lower in anchor.summary.lower():
                results.append(anchor)
                continue
            if any(keyword_lower in d.lower() for d in anchor.key_decisions):
                results.append(anchor)
        return results

    @property
    def size(self) -> int:
        return len(self._anchors)


class ArchivalMemory:
    """Long-term storage for old turns that have been compressed."""

    def __init__(self) -> None:
        self._turns: list[Turn] = []

    def archive(self, turns: list[Turn]) -> None:
        self._turns.extend(turns)

    def search(self, keyword: str, limit: int = 10) -> list[Turn]:
        keyword_lower = keyword.lower()
        results = []
        for turn in reversed(self._turns):
            if keyword_lower in turn.content.lower():
                results.append(turn)
                if len(results) >= limit:
                    break
        return results

    @property
    def size(self) -> int:
        return len(self._turns)


class MemoryManager:
    """Coordinates all three memory tiers."""

    def __init__(self, working_max: int = 50) -> None:
        self.working = WorkingMemory(max_turns=working_max)
        self.compressed = CompressedMemory()
        self.archival = ArchivalMemory()
        self._session_id: str | None = None
        self._turn_counter: int = 0

    def set_session(self, session_id: str) -> None:
        self._session_id = session_id

    def add_turn(self, role: str, content: str, persona: str = "user",
                 metadata: dict[str, Any] | None = None) -> Turn:
        """Add a turn to working memory."""
        turn = Turn(
            role=role,
            content=content,
            persona=persona,
            metadata=metadata or {},
        )
        self.working.add(turn)
        self._turn_counter += 1
        return turn

    def compress(self, anchor: CompressedAnchor) -> None:
        """Move old working memory turns to archival and store compression."""
        old_turns = self.working.get_recent()
        half = len(old_turns) // 2
        if half > 0:
            to_archive = old_turns[:half]
            self.archival.archive(to_archive)
        self.compressed.add(anchor)

    def build_context(self, max_working: int = 20, max_anchors: int = 3) -> str:
        """Build a context string from all memory tiers."""
        parts: list[str] = []

        # Add compressed anchors for background
        anchors = self.compressed.get_recent(max_anchors)
        if anchors:
            parts.append("=== Prior Context (Compressed) ===")
            for anchor in anchors:
                parts.append(f"Summary: {anchor.summary}")
                if anchor.key_decisions:
                    parts.append(f"Decisions: {'; '.join(anchor.key_decisions)}")
                if anchor.constraints:
                    parts.append(f"Constraints: {'; '.join(anchor.constraints)}")
                parts.append("")

        # Add recent working memory
        recent = self.working.get_recent(max_working)
        if recent:
            parts.append("=== Recent Conversation ===")
            for turn in recent:
                parts.append(f"[{turn.persona}/{turn.role}]: {turn.content}")

        return "\n".join(parts)

    def search(self, keyword: str, limit: int = 10) -> list[Turn]:
        """Search across all memory tiers."""
        results: list[Turn] = []
        # Search working memory
        for turn in self.working.get_recent():
            if keyword.lower() in turn.content.lower():
                results.append(turn)
        # Search archival
        results.extend(self.archival.search(keyword, limit=limit - len(results)))
        return results[:limit]

    def get_stats(self) -> dict[str, Any]:
        return {
            "session_id": self._session_id,
            "total_turns": self._turn_counter,
            "working_size": self.working.size,
            "compressed_anchors": self.compressed.size,
            "archival_size": self.archival.size,
        }
