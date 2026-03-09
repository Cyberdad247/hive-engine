"""Rating and rule extraction for HIVE Engine."""

from __future__ import annotations

import logging
from typing import Any

from core import router
from core.memory_db import MemoryDB

logger = logging.getLogger("hive.feedback")


class FeedbackEngine:
    """Manages ratings, extracts patterns from successful interactions,
    and injects learned rules into persona system prompts."""

    def __init__(self, db: MemoryDB) -> None:
        self.db = db

    def rate(self, session_id: str, direction: int, turn_id: int | None = None) -> None:
        """Record a +1 (thumbs up) or -1 (thumbs down) rating.

        Args:
            session_id: The session to rate.
            direction: +1 or -1.
            turn_id: Optional specific turn to rate.
        """
        if direction not in (1, -1):
            raise ValueError("direction must be +1 or -1")
        self.db.save_rating(session_id, direction, turn_id)
        logger.info("Rated session %s: %+d", session_id, direction)

    def extract_rules(self, session_id: str) -> list[str]:
        """Analyze highly-rated interactions in a session to extract reusable rules.

        Uses the Coda persona (tier 1) to identify patterns from turns
        that received positive ratings.
        """
        # Get all positive ratings for this session
        ratings = self.db.get_ratings(session_id)
        positive_turn_ids = {
            r["turn_id"] for r in ratings
            if r["direction"] > 0 and r["turn_id"] is not None
        }

        if not positive_turn_ids:
            # If no specific turns rated, look at all turns in positively-rated sessions
            net = sum(r["direction"] for r in ratings)
            if net <= 0:
                logger.info("No positive patterns found in session %s", session_id)
                return []
            # Use all turns from the session
            all_turns = self.db.search_turns("", session_id=session_id, limit=100)
            turn_texts = [
                f"[{t.persona}/{t.role}]: {t.content}" for t in all_turns
            ]
        else:
            # Get the specific positively-rated turns
            all_turns = self.db.search_turns("", session_id=session_id, limit=100)
            turn_texts = [
                f"[{t.persona}/{t.role}]: {t.content}"
                for t in all_turns
                if t.id in positive_turn_ids
            ]

        if not turn_texts:
            return []

        # Ask Coda to extract patterns
        conversation = "\n".join(turn_texts)
        extraction_prompt = (
            f"Analyze these positively-rated conversation turns and extract 1-5 "
            f"concise, actionable rules that explain what made them successful. "
            f"Return each rule on its own line, prefixed with '- '.\n\n"
            f"Turns:\n{conversation}"
        )

        try:
            result = router.route(
                "coda", extraction_prompt,
                system_prompt=(
                    "You are Coda, the compression engine. Extract reusable patterns "
                    "and rules from successful interactions. Be concise and specific."
                ),
            )
        except Exception as e:
            logger.error("Rule extraction failed: %s", e)
            return []

        # Parse rules from response
        rules: list[str] = []
        for line in result.strip().splitlines():
            line = line.strip()
            if line.startswith("- "):
                rule = line[2:].strip()
                if rule:
                    rules.append(rule)

        # Persist extracted rules
        for rule in rules:
            # Determine which persona the rule applies to
            persona = self._infer_persona_for_rule(rule, turn_texts)
            self.db.save_rule(persona, rule, source_session=session_id, confidence=0.7)
            logger.info("Extracted rule for %s: %s", persona, rule)

        return rules

    def _infer_persona_for_rule(self, rule: str, turn_texts: list[str]) -> str:
        """Infer which persona a rule is most relevant to."""
        persona_mentions: dict[str, int] = {}
        rule_lower = rule.lower()
        persona_keywords: dict[str, list[str]] = {
            "forge": ["code", "implement", "write", "function", "class", "generate"],
            "oracle": ["plan", "architect", "design", "structure", "dag"],
            "sentinel": ["security", "vulnerability", "scan", "check", "safe"],
            "debug": ["fix", "error", "bug", "heal", "debug", "traceback"],
            "muse": ["prompt", "rephrase", "variant", "creative", "optimize"],
            "coda": ["compress", "summarize", "anchor", "context"],
            "aegis": ["red team", "attack", "risk", "adversar"],
            "apis": ["browser", "test", "playwright", "crawl", "url"],
        }
        for persona, keywords in persona_keywords.items():
            score = sum(1 for kw in keywords if kw in rule_lower)
            if score > 0:
                persona_mentions[persona] = score

        if persona_mentions:
            return max(persona_mentions, key=persona_mentions.get)  # type: ignore[arg-type]
        return "forge"  # default

    def inject_rules(self, persona_name: str) -> str:
        """Return rules to prepend to a persona's system prompt.

        Fetches all stored rules for the persona, ordered by confidence,
        and formats them as a preamble.
        """
        rules = self.db.get_rules(persona_name.lower())
        if not rules:
            return ""

        lines = ["## Learned Rules (from past successful interactions)"]
        for r in rules:
            conf = r.get("confidence", 0.5)
            lines.append(f"- [{conf:.0%}] {r['rule']}")
        lines.append("")
        return "\n".join(lines)

    def get_session_score(self, session_id: str) -> int:
        """Get the net rating score for a session."""
        ratings = self.db.get_ratings(session_id)
        return sum(r["direction"] for r in ratings)
