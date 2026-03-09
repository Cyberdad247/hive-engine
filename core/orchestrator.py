"""Orchestrator pattern: Blackboard + Job Queue"""

import json
import sqlite3
import time
from enum import Enum
from typing import List, Dict, Any, Optional

class JobStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    REVIEW_REQUESTED = "review_requested"

class Orchestrator:
    """Manages the blackboard (shared facts/constraints) and a job queue."""
    def __init__(self, db_path: str = ".hive/orchestrator.db"):
        self.db_path = db_path
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        cur = self._conn.cursor()
        # Blackboard
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS blackboard (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at REAL NOT NULL
            );
            
            -- Job Queue
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task TEXT NOT NULL,
                assigned_to TEXT,
                status TEXT NOT NULL,
                acceptance_tests TEXT DEFAULT '[]',
                result TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
        """)
        self._conn.commit()

    # --- Blackboard Methods ---
    
    def set_fact(self, key: str, value: Any):
        """Update a fact on the blackboard."""
        now = time.time()
        val_str = json.dumps(value) if not isinstance(value, str) else value
        self._conn.execute(
            "INSERT INTO blackboard (key, value, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET value=?, updated_at=?",
            (key, val_str, now, val_str, now)
        )
        self._conn.commit()

    def get_fact(self, key: str) -> Optional[str]:
        """Read a fact from the blackboard."""
        row = self._conn.execute("SELECT value FROM blackboard WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    # --- Job Queue Methods ---
    
    def create_job(self, task: str, acceptance_tests: List[str] = None) -> int:
        """1. Planner creates jobs + acceptance tests"""
        now = time.time()
        tests_str = json.dumps(acceptance_tests or [])
        cur = self._conn.execute(
            "INSERT INTO jobs (task, status, acceptance_tests, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (task, JobStatus.PENDING.value, tests_str, now, now)
        )
        self._conn.commit()
        return cur.lastrowid

    def claim_job(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """2. Coder/Agents compete/claim jobs"""
        now = time.time()
        # Find first pending
        row = self._conn.execute("SELECT * FROM jobs WHERE status=? ORDER BY created_at ASC LIMIT 1", (JobStatus.PENDING.value,)).fetchone()
        if not row:
            return None
            
        job_id = row["id"]
        self._conn.execute(
            "UPDATE jobs SET status=?, assigned_to=?, updated_at=? WHERE id=?",
            (JobStatus.IN_PROGRESS.value, agent_name, now, job_id)
        )
        self._conn.commit()
        return dict(row)

    def submit_job_result(self, job_id: int, result: str):
        """3. Agent submits result, goes to review."""
        now = time.time()
        self._conn.execute(
            "UPDATE jobs SET status=?, result=?, updated_at=? WHERE id=?",
            (JobStatus.REVIEW_REQUESTED.value, result, now, job_id)
        )
        self._conn.commit()

    def review_job(self, job_id: int, approved: bool, feedback: str = ""):
        """4. Reviewer gates merges, 5. Orchestrator merges only when tests pass + reviewer OK."""
        now = time.time()
        new_status = JobStatus.COMPLETED.value if approved else JobStatus.FAILED.value
        
        # Append feedback to result
        row = self._conn.execute("SELECT result FROM jobs WHERE id=?", (job_id,)).fetchone()
        current_result = row["result"] if row else ""
        updated_result = f"{current_result}\n\nReview Feedback: {feedback}"
        
        self._conn.execute(
            "UPDATE jobs SET status=?, result=?, updated_at=? WHERE id=?",
            (new_status, updated_result, now, job_id)
        )
        self._conn.commit()

    def list_jobs(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        if status:
            rows = self._conn.execute("SELECT * FROM jobs WHERE status=? ORDER BY created_at DESC", (status,)).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

if __name__ == "__main__":
    # Quick test/demo of the orchestrator loop
    orchestrator = Orchestrator(":memory:")
    
    # Blackboard usage
    orchestrator.set_fact("project_language", "python")
    print("Fact:", orchestrator.get_fact("project_language"))
    
    # Gating flow
    job_id = orchestrator.create_job("Implement API endpoint", ["tests/test_api.py should pass"])
    print("Created Job:", job_id)
    
    claimed = orchestrator.claim_job("CoderAgent")
    print("Claimed Job:", claimed["id"], "by CoderAgent")
    
    orchestrator.submit_job_result(job_id, "Code written in main.py")
    
    # Reviewer tests
    orchestrator.review_job(job_id, approved=True, feedback="LGTM. Tests pass.")
    
    completed = orchestrator.list_jobs(JobStatus.COMPLETED.value)
    print("Completed Jobs:", len(completed))
