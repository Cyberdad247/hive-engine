"""SQLite persistence layer for HIVE Engine memory."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class TurnRecord:
    id: int
    session_id: str
    role: str
    content: str
    persona: str
    timestamp: float
    metadata: dict[str, Any]


@dataclass
class SessionRecord:
    id: str
    created_at: float
    updated_at: float
    summary: str


class MemoryDB:
    """SQLite-backed persistent memory store.

    DB path defaults to .hive/memory.db relative to CWD.
    """

    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            db_path = os.path.join(".hive", "memory.db")
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self.init_db()

    def init_db(self) -> None:
        """Create all 6 tables if they don't exist."""
        cur = self._conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                summary TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                persona TEXT NOT NULL DEFAULT 'user',
                timestamp REAL NOT NULL,
                metadata TEXT DEFAULT '{}',
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );

            CREATE TABLE IF NOT EXISTS rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                persona TEXT NOT NULL,
                rule TEXT NOT NULL,
                source_session TEXT,
                confidence REAL DEFAULT 0.5,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ratings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                turn_id INTEGER,
                direction INTEGER NOT NULL,
                timestamp REAL NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );

            CREATE TABLE IF NOT EXISTS compressions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                summary TEXT NOT NULL,
                key_decisions TEXT DEFAULT '[]',
                constraints TEXT DEFAULT '[]',
                assertions TEXT DEFAULT '[]',
                turn_start INTEGER,
                turn_end INTEGER,
                timestamp REAL NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );

            CREATE TABLE IF NOT EXISTS embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                turn_id INTEGER NOT NULL,
                vector TEXT NOT NULL,
                model TEXT DEFAULT 'local',
                created_at REAL NOT NULL,
                FOREIGN KEY (turn_id) REFERENCES turns(id)
            );

            CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id);
            CREATE INDEX IF NOT EXISTS idx_turns_persona ON turns(persona);
            CREATE INDEX IF NOT EXISTS idx_ratings_session ON ratings(session_id);
            CREATE INDEX IF NOT EXISTS idx_rules_persona ON rules(persona);
        """)
        self._conn.commit()

    def save_session(self, session_id: str, summary: str = "") -> None:
        """Create or update a session record."""
        now = time.time()
        self._conn.execute(
            """INSERT INTO sessions (id, created_at, updated_at, summary)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET updated_at=?, summary=?""",
            (session_id, now, now, summary, now, summary),
        )
        self._conn.commit()

    def save_turn(self, session_id: str, role: str, content: str,
                  persona: str = "user", metadata: dict[str, Any] | None = None) -> int:
        """Save a conversation turn and return its row id."""
        now = time.time()
        meta_json = json.dumps(metadata or {})
        cur = self._conn.execute(
            """INSERT INTO turns (session_id, role, content, persona, timestamp, metadata)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, role, content, persona, now, meta_json),
        )
        # Update session timestamp
        self._conn.execute(
            "UPDATE sessions SET updated_at=? WHERE id=?", (now, session_id)
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def save_rating(self, session_id: str, direction: int, turn_id: int | None = None) -> None:
        """Save a thumbs-up (+1) or thumbs-down (-1) rating."""
        now = time.time()
        self._conn.execute(
            """INSERT INTO ratings (session_id, turn_id, direction, timestamp)
               VALUES (?, ?, ?, ?)""",
            (session_id, turn_id, direction, now),
        )
        self._conn.commit()

    def save_rule(self, persona: str, rule: str, source_session: str | None = None,
                  confidence: float = 0.5) -> int:
        """Save an extracted rule for a persona."""
        now = time.time()
        cur = self._conn.execute(
            """INSERT INTO rules (persona, rule, source_session, confidence, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (persona, rule, source_session, confidence, now),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def save_compression(self, session_id: str, summary: str,
                         key_decisions: list[str], constraints: list[str],
                         assertions: list[str],
                         turn_start: int | None = None,
                         turn_end: int | None = None) -> int:
        """Save a Coda compression anchor."""
        now = time.time()
        cur = self._conn.execute(
            """INSERT INTO compressions
               (session_id, summary, key_decisions, constraints, assertions,
                turn_start, turn_end, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, summary, json.dumps(key_decisions),
             json.dumps(constraints), json.dumps(assertions),
             turn_start, turn_end, now),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def save_embedding(self, turn_id: int, vector: list[float],
                       model: str = "local") -> int:
        """Save an embedding vector for a turn."""
        now = time.time()
        cur = self._conn.execute(
            """INSERT INTO embeddings (turn_id, vector, model, created_at)
               VALUES (?, ?, ?, ?)""",
            (turn_id, json.dumps(vector), model, now),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def search_turns(self, query: str, persona: str | None = None,
                     session_id: str | None = None,
                     limit: int = 20) -> list[TurnRecord]:
        """Full-text search across turns."""
        sql = "SELECT * FROM turns WHERE content LIKE ?"
        params: list[Any] = [f"%{query}%"]
        if persona:
            sql += " AND persona = ?"
            params.append(persona)
        if session_id:
            sql += " AND session_id = ?"
            params.append(session_id)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [
            TurnRecord(
                id=r["id"],
                session_id=r["session_id"],
                role=r["role"],
                content=r["content"],
                persona=r["persona"],
                timestamp=r["timestamp"],
                metadata=json.loads(r["metadata"]),
            )
            for r in rows
        ]

    def get_rules(self, persona: str) -> list[dict[str, Any]]:
        """Get all rules for a persona, ordered by confidence."""
        rows = self._conn.execute(
            "SELECT * FROM rules WHERE persona = ? ORDER BY confidence DESC",
            (persona,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_ratings(self, session_id: str) -> list[dict[str, Any]]:
        """Get all ratings for a session."""
        rows = self._conn.execute(
            "SELECT * FROM ratings WHERE session_id = ? ORDER BY timestamp",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_sessions(self, limit: int = 20) -> list[SessionRecord]:
        """Get recent sessions."""
        rows = self._conn.execute(
            "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            SessionRecord(
                id=r["id"], created_at=r["created_at"],
                updated_at=r["updated_at"], summary=r["summary"],
            )
            for r in rows
        ]

    def get_stats(self) -> dict[str, Any]:
        """Return aggregate stats across all tables."""
        stats: dict[str, Any] = {}
        for table in ("sessions", "turns", "rules", "ratings", "compressions", "embeddings"):
            row = self._conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
            stats[f"{table}_count"] = row["cnt"]

        # Rating summary
        row = self._conn.execute(
            "SELECT COALESCE(SUM(direction), 0) as net FROM ratings"
        ).fetchone()
        stats["net_rating"] = row["net"]

        # Most active persona
        row = self._conn.execute(
            """SELECT persona, COUNT(*) as cnt FROM turns
               GROUP BY persona ORDER BY cnt DESC LIMIT 1"""
        ).fetchone()
        if row:
            stats["top_persona"] = row["persona"]
            stats["top_persona_turns"] = row["cnt"]

        return stats

    def close(self) -> None:
        self._conn.close()
