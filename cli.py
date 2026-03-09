"""HIVE Engine CLI -- Multi-agent orchestration interface."""

from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from typing import Any

from core.feedback import FeedbackEngine
from core.memory import MemoryManager
from core.memory_db import MemoryDB
from core.pipeline import Pipeline
from personas.aegis import Aegis
from personas.apis import Apis
from personas.coda import Coda
from personas.debug import Debug
from personas.forge import Forge
from personas.muse import Muse
from personas.oracle import Oracle
from personas.sentinel import Sentinel

# Persona emoji map
EMOJI: dict[str, str] = {
    "forge": "\U0001f525",     # fire
    "oracle": "\U0001f52e",    # crystal ball
    "sentinel": "\U0001f6e1\ufe0f",  # shield
    "debug": "\U0001f41b",     # bug
    "muse": "\U0001f3a8",      # palette
    "coda": "\U0001f4e6",      # package
    "aegis": "\u2694\ufe0f",   # swords
    "apis": "\U0001f310",      # globe
    "pipeline": "\u2699\ufe0f", # gear
    "hive": "\U0001f41d",      # bee
}

HELP_TEXT = """\
HIVE Engine Commands:
  /run <task>       Run full pipeline (Oracle->Forge->Sentinel+Aegis)
  /forge <prompt>   Generate code with Forge
  /oracle <prompt>  Plan a task with Oracle
  /sentinel <code>  Security review with Sentinel
  /heal <file|code> Auto-heal with Debug
  /muse <prompt>    Optimize a prompt with Muse
  /compress <text>  Compress with Coda
  /aegis <code>     Red team review with Aegis
  /apis <url>       Generate Playwright test with Apis
  /rate +           Thumbs up last interaction
  /rate -           Thumbs down last interaction
  /learn            Extract rules from rated sessions
  /search <query>   Search memory
  /history          Show recent turns
  /stats            Show memory and session stats
  /resume           Resume last session
  /help             Show this help
  /quit             Exit HIVE Engine
"""


class HiveCLI:
    """Main CLI controller."""

    def __init__(self) -> None:
        self.db = MemoryDB()
        self.memory = MemoryManager()
        self.feedback = FeedbackEngine(self.db)
        self.pipeline = Pipeline()

        # Initialize personas
        self.forge = Forge()
        self.oracle = Oracle()
        self.sentinel = Sentinel()
        self.debug = Debug()
        self.muse = Muse()
        self.coda = Coda()
        self.aegis = Aegis()
        self.apis = Apis()

        self.session_id = str(uuid.uuid4())[:8]
        self.db.save_session(self.session_id)
        self.memory.set_session(self.session_id)

    def _print(self, persona: str, message: str) -> None:
        emoji = EMOJI.get(persona, "\U0001f41d")
        print(f"\n{emoji} [{persona.upper()}]: {message}")

    def _save_turn(self, role: str, content: str, persona: str) -> None:
        self.memory.add_turn(role, content, persona)
        self.db.save_turn(self.session_id, role, content, persona)

    async def _handle_run(self, task: str) -> None:
        self._print("pipeline", f"Running full pipeline for: {task[:80]}...")
        self._save_turn("user", task, "pipeline")
        result = await self.pipeline.run(task)

        self._print("oracle", f"Plan:\n{result.plan[:500]}")
        self._print("forge", f"Code:\n{result.code[:500]}")
        self._print("sentinel", f"Security Review:\n{result.security_review[:500]}")
        self._print("aegis", f"Red Team Review:\n{result.red_team_review[:500]}")

        if not result.success:
            self._print("pipeline", f"Errors: {', '.join(result.errors)}")

        self._save_turn("assistant", json.dumps({
            "plan": result.plan[:200],
            "success": result.success,
        }), "pipeline")

    async def _handle_forge(self, prompt: str) -> None:
        self._save_turn("user", prompt, "forge")
        try:
            result = self.forge.process(prompt)
            self._print("forge", result)
            self._save_turn("assistant", result, "forge")
        except Exception as e:
            self._print("forge", f"Error: {e}")

    async def _handle_oracle(self, prompt: str) -> None:
        self._save_turn("user", prompt, "oracle")
        try:
            result = self.oracle.process(prompt)
            self._print("oracle", json.dumps(result, indent=2))
            self._save_turn("assistant", json.dumps(result), "oracle")
        except Exception as e:
            self._print("oracle", f"Error: {e}")

    async def _handle_sentinel(self, content: str) -> None:
        self._save_turn("user", content[:200], "sentinel")
        try:
            result = self.sentinel.process(content)
            output = (
                f"Overall Risk: {result.overall_risk}\n"
                f"Passed: {result.passed}\n"
                f"Summary: {result.summary}\n"
                f"Findings ({len(result.findings)}):\n"
            )
            for f in result.findings:
                output += f"  - [{f.severity}] {f.issue}"
                if f.line_hint:
                    output += f" (near: {f.line_hint})"
                output += "\n"
            self._print("sentinel", output)
            self._save_turn("assistant", output, "sentinel")
        except Exception as e:
            self._print("sentinel", f"Error: {e}")

    async def _handle_heal(self, target: str) -> None:
        self._save_turn("user", target, "debug")
        try:
            result = self.debug.process(target)
            status = "SUCCESS" if result.success else "FAILED"
            output = f"Status: {status} ({len(result.attempts)} attempts)"
            if result.final_error:
                output += f"\nFinal error: {result.final_error}"
            if result.final_code:
                output += f"\nFinal code:\n{result.final_code[:500]}"
            self._print("debug", output)
            self._save_turn("assistant", output, "debug")
        except Exception as e:
            self._print("debug", f"Error: {e}")

    async def _handle_muse(self, prompt: str) -> None:
        self._save_turn("user", prompt, "muse")
        try:
            result = self.muse.process(prompt)
            output = (
                f"PRECISE:\n{result.precise}\n\n"
                f"CONSTRAINED:\n{result.constrained}\n\n"
                f"CREATIVE:\n{result.creative}"
            )
            self._print("muse", output)
            self._save_turn("assistant", output, "muse")
        except Exception as e:
            self._print("muse", f"Error: {e}")

    async def _handle_compress(self, text: str) -> None:
        self._save_turn("user", text[:200], "coda")
        try:
            result = self.coda.process(text)
            output = (
                f"Summary: {result.summary}\n"
                f"Key Decisions: {', '.join(result.key_decisions) or 'none'}\n"
                f"Constraints: {', '.join(result.constraints) or 'none'}\n"
                f"Assertions: {', '.join(result.assertions) or 'none'}"
            )
            self._print("coda", output)
            self._save_turn("assistant", output, "coda")
        except Exception as e:
            self._print("coda", f"Error: {e}")

    async def _handle_aegis(self, content: str) -> None:
        self._save_turn("user", content[:200], "aegis")
        try:
            result = self.aegis.process(content)
            output = (
                f"Risk Score: {result.risk_score}/100\n"
                f"Verdict: {result.verdict}\n"
                f"Findings ({len(result.findings)}):\n"
            )
            for f in result.findings:
                output += f"  - {f}\n"
            self._print("aegis", output)
            self._save_turn("assistant", output, "aegis")
        except Exception as e:
            self._print("aegis", f"Error: {e}")

    async def _handle_apis(self, url: str) -> None:
        self._save_turn("user", url, "apis")
        try:
            result = self.apis.process(url)
            self._print("apis", result)
            self._save_turn("assistant", result, "apis")
        except Exception as e:
            self._print("apis", f"Error: {e}")

    async def _handle_rate(self, direction_str: str) -> None:
        direction = 1 if direction_str.strip() == "+" else -1
        self.feedback.rate(self.session_id, direction)
        label = "thumbs up" if direction > 0 else "thumbs down"
        self._print("hive", f"Rated session {self.session_id}: {label}")

    async def _handle_learn(self) -> None:
        rules = self.feedback.extract_rules(self.session_id)
        if rules:
            self._print("hive", f"Extracted {len(rules)} rules:\n" +
                        "\n".join(f"  - {r}" for r in rules))
        else:
            self._print("hive", "No rules extracted (need positive ratings first).")

    async def _handle_search(self, query: str) -> None:
        turns = self.memory.search(query)
        db_turns = self.db.search_turns(query)
        all_results = len(turns) + len(db_turns)
        output = f"Found {all_results} results for '{query}':\n"
        for t in turns[:10]:
            output += f"  [{t.persona}] {t.content[:100]}\n"
        for t in db_turns[:10]:
            output += f"  [{t.persona}] {t.content[:100]}\n"
        self._print("hive", output)

    async def _handle_history(self) -> None:
        turns = self.memory.working.get_recent(20)
        if not turns:
            self._print("hive", "No turns in current session.")
            return
        output = f"Last {len(turns)} turns:\n"
        for t in turns:
            ts = time.strftime("%H:%M:%S", time.localtime(t.timestamp))
            output += f"  [{ts}] {EMOJI.get(t.persona, '')} {t.persona}/{t.role}: {t.content[:80]}\n"
        self._print("hive", output)

    async def _handle_stats(self) -> None:
        mem_stats = self.memory.get_stats()
        db_stats = self.db.get_stats()
        output = "Memory Stats:\n"
        for k, v in mem_stats.items():
            output += f"  {k}: {v}\n"
        output += "\nDatabase Stats:\n"
        for k, v in db_stats.items():
            output += f"  {k}: {v}\n"
        self._print("hive", output)

    async def _handle_resume(self) -> None:
        sessions = self.db.get_sessions(limit=1)
        if sessions and sessions[0].id != self.session_id:
            old = sessions[0]
            self.session_id = old.id
            self.memory.set_session(old.id)
            self._print("hive", f"Resumed session {old.id} (last updated: "
                        f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(old.updated_at))})")
        else:
            self._print("hive", "No previous session to resume.")

    async def dispatch(self, line: str) -> bool:
        """Parse and dispatch a command. Returns False to quit."""
        line = line.strip()
        if not line:
            return True

        if line.startswith("/"):
            parts = line.split(None, 1)
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""

            handlers: dict[str, Any] = {
                "/run": lambda: self._handle_run(arg),
                "/forge": lambda: self._handle_forge(arg),
                "/oracle": lambda: self._handle_oracle(arg),
                "/sentinel": lambda: self._handle_sentinel(arg),
                "/heal": lambda: self._handle_heal(arg),
                "/muse": lambda: self._handle_muse(arg),
                "/compress": lambda: self._handle_compress(arg),
                "/aegis": lambda: self._handle_aegis(arg),
                "/apis": lambda: self._handle_apis(arg),
                "/rate": lambda: self._handle_rate(arg),
                "/learn": lambda: self._handle_learn(),
                "/search": lambda: self._handle_search(arg),
                "/history": lambda: self._handle_history(),
                "/stats": lambda: self._handle_stats(),
                "/resume": lambda: self._handle_resume(),
                "/help": None,
                "/quit": None,
            }

            if cmd == "/quit":
                self._print("hive", "Goodbye!")
                return False
            elif cmd == "/help":
                print(HELP_TEXT)
                return True
            elif cmd in handlers:
                if not arg and cmd in ("/run", "/forge", "/oracle", "/sentinel",
                                       "/heal", "/muse", "/compress", "/aegis",
                                       "/apis", "/search"):
                    self._print("hive", f"Usage: {cmd} <argument>")
                else:
                    await handlers[cmd]()
            else:
                self._print("hive", f"Unknown command: {cmd}. Type /help for commands.")
        else:
            # Default: treat as forge prompt
            await self._handle_forge(line)

        return True

    async def run(self) -> None:
        """Main input loop."""
        print(f"\n{EMOJI['hive']} HIVE Engine v0.1.0 | Session: {self.session_id}")
        print("Type /help for commands, /quit to exit.\n")

        while True:
            try:
                line = await asyncio.to_thread(input, f"{EMOJI['hive']} > ")
            except (EOFError, KeyboardInterrupt):
                self._print("hive", "Goodbye!")
                break

            should_continue = await self.dispatch(line)
            if not should_continue:
                break

        self.db.close()


def main() -> None:
    cli = HiveCLI()
    try:
        asyncio.run(cli.run())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        cli.db.close()


if __name__ == "__main__":
    main()
