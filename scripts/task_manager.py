"""TASK.md lifecycle manager for HIVE Engine."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
HIVE_DIR = PROJECT_ROOT / ".hive"
TASKS_JSON = HIVE_DIR / "tasks.json"
TASK_MD = PROJECT_ROOT / "TASK.md"


@dataclass
class Task:
    id: int
    persona: str
    description: str
    priority: str  # low, medium, high, critical
    status: str = "todo"  # todo, in_progress, done, blocked
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    completed_at: float | None = None


class TaskStore:
    """JSON-backed task storage."""

    def __init__(self) -> None:
        HIVE_DIR.mkdir(parents=True, exist_ok=True)
        self.tasks: list[Task] = []
        self._next_id: int = 1
        self._load()

    def _load(self) -> None:
        if TASKS_JSON.exists():
            try:
                data = json.loads(TASKS_JSON.read_text())
                self.tasks = [Task(**t) for t in data.get("tasks", [])]
                self._next_id = data.get("next_id", 1)
            except (json.JSONDecodeError, TypeError):
                self.tasks = []
                self._next_id = 1

    def _save(self) -> None:
        data = {
            "next_id": self._next_id,
            "tasks": [asdict(t) for t in self.tasks],
        }
        TASKS_JSON.write_text(json.dumps(data, indent=2))

    def add(self, persona: str, description: str, priority: str = "medium") -> Task:
        task = Task(
            id=self._next_id,
            persona=persona.lower(),
            description=description,
            priority=priority.lower(),
        )
        self.tasks.append(task)
        self._next_id += 1
        self._save()
        self._generate_md()
        return task

    def start(self, task_id: int) -> Task | None:
        task = self._find(task_id)
        if task:
            task.status = "in_progress"
            task.updated_at = time.time()
            self._save()
            self._generate_md()
        return task

    def done(self, task_id: int) -> Task | None:
        task = self._find(task_id)
        if task:
            task.status = "done"
            task.updated_at = time.time()
            task.completed_at = time.time()
            self._save()
            self._generate_md()
        return task

    def list_tasks(self, persona: str | None = None) -> list[Task]:
        tasks = self.tasks
        if persona:
            tasks = [t for t in tasks if t.persona == persona.lower()]
        return sorted(tasks, key=lambda t: (
            {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(t.priority, 2),
            {"in_progress": 0, "todo": 1, "blocked": 2, "done": 3}.get(t.status, 1),
        ))

    def status_summary(self) -> dict[str, int]:
        summary: dict[str, int] = {"todo": 0, "in_progress": 0, "done": 0, "blocked": 0}
        for t in self.tasks:
            summary[t.status] = summary.get(t.status, 0) + 1
        return summary

    def _find(self, task_id: int) -> Task | None:
        for t in self.tasks:
            if t.id == task_id:
                return t
        return None

    def _generate_md(self) -> None:
        """Generate TASK.md from current task state."""
        lines = ["# HIVE Engine Tasks", ""]

        # Group by status
        for status_label, status_key in [
            ("In Progress", "in_progress"),
            ("To Do", "todo"),
            ("Blocked", "blocked"),
            ("Done", "done"),
        ]:
            group = [t for t in self.tasks if t.status == status_key]
            if not group:
                continue

            lines.append(f"## {status_label}")
            lines.append("")
            lines.append("| ID | Persona | Priority | Description |")
            lines.append("|-----|---------|----------|-------------|")
            for t in sorted(group, key=lambda x: (
                {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(x.priority, 2),
            )):
                priority_badge = {
                    "critical": "**CRITICAL**",
                    "high": "HIGH",
                    "medium": "medium",
                    "low": "low",
                }.get(t.priority, t.priority)
                lines.append(f"| {t.id} | {t.persona} | {priority_badge} | {t.description} |")
            lines.append("")

        # Summary
        summary = self.status_summary()
        total = sum(summary.values())
        lines.append("---")
        lines.append(f"*{total} total: {summary['in_progress']} in progress, "
                      f"{summary['todo']} todo, {summary['done']} done, "
                      f"{summary['blocked']} blocked*")
        lines.append("")

        TASK_MD.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="HIVE task manager")
    sub = parser.add_subparsers(dest="command")

    list_parser = sub.add_parser("list", help="List tasks")
    list_parser.add_argument("persona", nargs="?", help="Filter by persona")

    add_parser = sub.add_parser("add", help="Add a task")
    add_parser.add_argument("persona", help="Persona to assign")
    add_parser.add_argument("description", help="Task description")
    add_parser.add_argument("priority", nargs="?", default="medium",
                            choices=["low", "medium", "high", "critical"],
                            help="Priority (default: medium)")

    start_parser = sub.add_parser("start", help="Start a task")
    start_parser.add_argument("id", type=int, help="Task ID")

    done_parser = sub.add_parser("done", help="Complete a task")
    done_parser.add_argument("id", type=int, help="Task ID")

    sub.add_parser("status", help="Show status summary")

    args = parser.parse_args()
    store = TaskStore()

    if args.command == "list" or args.command is None:
        tasks = store.list_tasks(getattr(args, "persona", None))
        if not tasks:
            print("No tasks found.")
            return
        print(f"{'ID':>4}  {'Status':<12}  {'Persona':<10}  {'Priority':<10}  Description")
        print("-" * 72)
        for t in tasks:
            print(f"{t.id:>4}  {t.status:<12}  {t.persona:<10}  {t.priority:<10}  {t.description}")

    elif args.command == "add":
        task = store.add(args.persona, args.description, args.priority)
        print(f"Created task #{task.id}: [{task.persona}] {task.description} ({task.priority})")

    elif args.command == "start":
        task = store.start(args.id)
        if task:
            print(f"Started task #{task.id}: {task.description}")
        else:
            print(f"Task #{args.id} not found.", file=sys.stderr)
            sys.exit(1)

    elif args.command == "done":
        task = store.done(args.id)
        if task:
            print(f"Completed task #{task.id}: {task.description}")
        else:
            print(f"Task #{args.id} not found.", file=sys.stderr)
            sys.exit(1)

    elif args.command == "status":
        summary = store.status_summary()
        total = sum(summary.values())
        print(f"Task Status ({total} total):")
        for status, count in summary.items():
            bar = "#" * count
            print(f"  {status:<12}  {count:>3}  {bar}")


if __name__ == "__main__":
    main()
