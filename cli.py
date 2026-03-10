"""HIVE Engine CLI -- Rich HUD terminal interface using only stdlib."""

from __future__ import annotations

import os
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import asyncio
import ctypes
import dataclasses
import json
import shutil
import sys
import time
import uuid
from typing import Any

from core.feedback import FeedbackEngine
from core.memory import MemoryManager
from core.memory_db import MemoryDB
from core.pipeline import Pipeline
from core import router
from personas.aegis import Aegis
from personas.apis import Apis
from personas.coda import Coda
from personas.debug import Debug
from personas.forge import Forge
from personas.muse import Muse
from personas.oracle import Oracle
from personas.sentinel import Sentinel

# ─── Enable Windows VT100 escape sequences ─────────────────────────
def _enable_vt100() -> None:
    """Enable ANSI/VT100 escape codes on Windows via ctypes."""
    if sys.platform == "win32":
        try:
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            STD_OUTPUT_HANDLE = -11
            ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)
        except Exception:
            pass  # Not a real Windows console (e.g. piped)

_enable_vt100()

# ─── ANSI Color Codes ──────────────────────────────────────────────
class C:
    """ANSI escape code constants."""
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    ITALIC  = "\033[3m"
    UNDERLINE = "\033[4m"
    BLINK   = "\033[5m"
    REVERSE = "\033[7m"

    BLACK   = "\033[30m"
    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN    = "\033[36m"
    WHITE   = "\033[37m"

    BG_BLACK   = "\033[40m"
    BG_RED     = "\033[41m"
    BG_GREEN   = "\033[42m"
    BG_YELLOW  = "\033[43m"
    BG_BLUE    = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN    = "\033[46m"
    BG_WHITE   = "\033[47m"

    # 256-color
    ORANGE  = "\033[38;5;208m"
    PINK    = "\033[38;5;213m"
    LIME    = "\033[38;5;118m"
    TEAL    = "\033[38;5;37m"
    GOLD    = "\033[38;5;220m"
    PURPLE  = "\033[38;5;135m"
    SKY     = "\033[38;5;117m"
    CORAL   = "\033[38;5;209m"

    CLEAR_SCREEN = "\033[2J\033[H"
    CLEAR_LINE   = "\033[2K"
    HIDE_CURSOR  = "\033[?25l"
    SHOW_CURSOR  = "\033[?25h"

# ─── Persona Config ────────────────────────────────────────────────
EMOJI: dict[str, str] = {
    "forge":    "\U0001f525",      # fire
    "oracle":   "\U0001f52e",      # crystal ball
    "sentinel": "\U0001f6e1\ufe0f",# shield
    "debug":    "\U0001f41b",      # bug
    "muse":     "\U0001f3a8",      # palette
    "coda":     "\U0001f4e6",      # package
    "aegis":    "\u2694\ufe0f",    # swords
    "apis":     "\U0001f310",      # globe
    "pipeline": "\u2699\ufe0f",    # gear
    "hive":     "\U0001f41d",      # bee
}

PERSONA_COLORS: dict[str, str] = {
    "forge":    C.ORANGE,
    "oracle":   C.PURPLE,
    "sentinel": C.TEAL,
    "debug":    C.RED,
    "muse":     C.PINK,
    "coda":     C.CYAN,
    "aegis":    C.CORAL,
    "apis":     C.SKY,
    "pipeline": C.GOLD,
    "hive":     C.YELLOW,
}

PERSONA_NAMES = ["oracle", "forge", "sentinel", "debug", "muse", "coda", "aegis", "apis"]

VERSION = "0.3.0"

HELP_TEXT = """\
HIVE Engine Commands:
  /run <task>         Run full pipeline (Oracle->Forge->Sentinel+Aegis)

  Forge:
  /forge <prompt>     Generate code with Forge
  /refactor <code>    Refactor code with Forge
  /tests <code>       Generate tests with Forge
  /convert <lang> <code>  Convert code to another language with Forge
  /document <code>    Document code with Forge

  Oracle:
  /oracle <prompt>    Plan a task with Oracle
  /deps <description> Dependency analysis with Oracle
  /diagram <description>  Architecture diagram with Oracle
  /estimate <task>    Estimate effort with Oracle

  Sentinel:
  /sentinel <code>    Security review with Sentinel
  /scandeps <requirements>  Scan dependencies with Sentinel
  /owasp <code>       OWASP checklist with Sentinel
  /compliance <code>  Compliance check with Sentinel

  Debug:
  /heal <file|code>   Auto-heal with Debug
  /profile <code>     Profile performance with Debug
  /trace <error>      Trace error with Debug
  /stacktrace <trace> Explain stacktrace with Debug

  Muse:
  /muse <prompt>      Optimize a prompt with Muse
  /mockup <description>   UI mockup with Muse
  /naming <description>   Naming suggestions with Muse
  /brainstorm <topic> Brainstorm ideas with Muse

  Coda:
  /compress <text>    Compress with Coda
  /changelog <diff>   Generate changelog with Coda
  /diff <diff>        Diff summary with Coda
  /meeting <transcript>   Meeting notes with Coda

  Aegis:
  /aegis <code>       Red team review with Aegis
  /threat <description>   Threat model with Aegis
  /fuzz <code>        Fuzz inputs with Aegis
  /surface <description>  Attack surface map with Aegis

  Apis:
  /apis <url>         Generate Playwright test with Apis
  /contract <spec>    API contract validation with Apis
  /loadtest <url>     Load test with Apis
  /mockserver <spec>  Mock server with Apis

  General:
  /rate +             Thumbs up last interaction
  /rate -             Thumbs down last interaction
  /learn              Extract rules from rated sessions
  /search <query>     Search memory
  /history            Show recent turns
  /stats              Show memory and session stats
  /resume             Resume last session
  /provider <name>    Switch provider (gemini/openai/anthropic/ollama)
  /status             Show system status panel
  /hud                Toggle HUD mode on/off
  /help               Show this help
  /quit               Exit HIVE Engine
"""


# ─── Box Drawing Helpers ──────────────────────────────────────────
def _term_width() -> int:
    """Get terminal width, default 100."""
    try:
        return shutil.get_terminal_size((100, 30)).columns
    except Exception:
        return 100


def box_top(width: int, title: str = "") -> str:
    if title:
        title_str = f" {title} "
        remaining = width - 2 - len(title_str)
        left = 2
        right = max(remaining - left, 0)
        return f"\u250c{'─' * left}{C.BOLD}{C.YELLOW}{title_str}{C.RESET}{'─' * right}\u2510"
    return f"\u250c{'─' * (width - 2)}\u2510"


def box_mid(width: int, title: str = "") -> str:
    if title:
        title_str = f" {title} "
        remaining = width - 2 - len(title_str)
        left = 2
        right = max(remaining - left, 0)
        return f"\u251c{'─' * left}{C.DIM}{title_str}{C.RESET}{'─' * right}\u2524"
    return f"\u251c{'─' * (width - 2)}\u2524"


def box_bottom(width: int) -> str:
    return f"\u2514{'─' * (width - 2)}\u2518"


def box_line(width: int, text: str, pad: int = 1) -> str:
    """Render a line inside a box. Strips ANSI for width calc."""
    inner = width - 2 - (pad * 2)
    # Strip ANSI codes for length calculation
    stripped = text
    i = 0
    clean = []
    while i < len(stripped):
        if stripped[i] == '\033':
            # Skip to 'm'
            while i < len(stripped) and stripped[i] != 'm':
                i += 1
            i += 1  # skip 'm'
        else:
            clean.append(stripped[i])
            i += 1
    visible_len = len(clean)
    padding_needed = max(inner - visible_len, 0)
    return f"\u2502{' ' * pad}{text}{' ' * padding_needed}{' ' * pad}\u2502"


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    result = []
    i = 0
    while i < len(text):
        if text[i] == '\033':
            while i < len(text) and text[i] != 'm':
                i += 1
            i += 1
        else:
            result.append(text[i])
            i += 1
    return "".join(result)


# ─── HUD Renderer ─────────────────────────────────────────────────
class HUD:
    """Renders the rich terminal HUD."""

    def __init__(self, cli: "HiveCLI") -> None:
        self.cli = cli
        self.enabled = True
        self.output_history: list[tuple[str, str]] = []  # (persona, text)
        self.max_history = 20
        self.persona_status: dict[str, str] = {p: "idle" for p in PERSONA_NAMES}
        self._start_time = time.time()

    def toggle(self) -> bool:
        self.enabled = not self.enabled
        return self.enabled

    def _status_icon(self, status: str) -> str:
        icons = {
            "idle":    f"{C.DIM}\u25cb{C.RESET}",
            "working": f"{C.YELLOW}\u25d4{C.RESET}",
            "done":    f"{C.GREEN}\u2713{C.RESET}",
            "error":   f"{C.RED}\u2717{C.RESET}",
        }
        return icons.get(status, f"{C.DIM}?{C.RESET}")

    def set_persona_status(self, persona: str, status: str) -> None:
        self.persona_status[persona.lower()] = status

    def add_output(self, persona: str, text: str) -> None:
        self.output_history.append((persona, text))
        if len(self.output_history) > self.max_history:
            self.output_history = self.output_history[-self.max_history:]

    def uptime(self) -> str:
        elapsed = int(time.time() - self._start_time)
        mins, secs = divmod(elapsed, 60)
        hours, mins = divmod(mins, 60)
        if hours:
            return f"{hours}h {mins}m {secs}s"
        elif mins:
            return f"{mins}m {secs}s"
        return f"{secs}s"

    def render_header(self, width: int) -> list[str]:
        """Render the header panel."""
        lines = []
        lines.append(box_top(width, "HIVE ENGINE"))

        # Logo line
        logo = (
            f"{C.BOLD}{C.YELLOW}\U0001f41d HIVE Engine{C.RESET} "
            f"{C.DIM}v{VERSION}{C.RESET}"
        )
        lines.append(box_line(width, logo))

        # Session & timestamp
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        session_line = (
            f"{C.DIM}Session:{C.RESET} {C.CYAN}{self.cli.session_id}{C.RESET}"
            f"  {C.DIM}|{C.RESET}  {C.DIM}Time:{C.RESET} {ts}"
        )
        lines.append(box_line(width, session_line))

        # Provider & model info
        provider = os.environ.get("HIVE_PROVIDER", "gemini").lower()
        ladder = router.LADDERS.get(provider, {})
        tier_info = f"T1={ladder.get(1, '?')} T2={ladder.get(2, '?')} T3={ladder.get(3, '?')}"
        prov_line = (
            f"{C.DIM}Provider:{C.RESET} {C.GREEN}{provider}{C.RESET}"
            f"  {C.DIM}|{C.RESET}  {C.DIM}Models:{C.RESET} {C.DIM}{tier_info}{C.RESET}"
        )
        lines.append(box_line(width, prov_line))

        return lines

    def render_persona_bar(self, width: int, active: str = "") -> list[str]:
        """Render the persona status bar."""
        lines = []
        lines.append(box_mid(width, "PERSONAS"))

        # Build persona cells
        cells = []
        for p in PERSONA_NAMES:
            emoji = EMOJI.get(p, "?")
            color = PERSONA_COLORS.get(p, C.WHITE)
            status_icon = self._status_icon(self.persona_status.get(p, "idle"))
            name = p.capitalize()
            if p == active.lower():
                cell = f"{C.REVERSE}{color}{emoji} {name}{C.RESET} {status_icon}"
            else:
                cell = f"{color}{emoji} {name}{C.RESET} {status_icon}"
            cells.append(cell)

        # Join cells with separators
        bar = "  ".join(cells)
        lines.append(box_line(width, bar))

        return lines

    def render_pipeline_progress(self, width: int, steps: list[dict]) -> list[str]:
        """Render pipeline step progress."""
        lines = []
        lines.append(box_mid(width, "PIPELINE"))

        for step in steps:
            idx = step.get("index", 0)
            total = step.get("total", 4)
            persona = step.get("persona", "?")
            status = step.get("status", "pending")
            elapsed = step.get("elapsed", 0.0)
            parallel = step.get("parallel", False)

            color = PERSONA_COLORS.get(persona.lower(), C.WHITE)
            emoji = EMOJI.get(persona.lower(), "?")
            par_tag = " (parallel)" if parallel else ""

            if status == "done":
                status_str = f"{C.GREEN}Done \u2713{C.RESET}"
            elif status == "working":
                status_str = f"{C.YELLOW}Working...{C.RESET}"
            elif status == "error":
                status_str = f"{C.RED}Error \u2717{C.RESET}"
            else:
                status_str = f"{C.DIM}Pending{C.RESET}"

            time_str = f"{C.DIM}{elapsed:.1f}s{C.RESET}" if elapsed > 0 else ""

            line_text = (
                f"{C.DIM}[{idx}/{total}]{C.RESET} "
                f"{color}{emoji} {persona.capitalize()}{C.RESET}: "
                f"{status_str}{par_tag} {time_str}"
            )
            lines.append(box_line(width, line_text))

        return lines

    def render_output(self, width: int, n: int = 5) -> list[str]:
        """Render the last N outputs."""
        lines = []
        lines.append(box_mid(width, "OUTPUT"))

        recent = self.output_history[-n:] if self.output_history else []
        if not recent:
            lines.append(box_line(width, f"{C.DIM}No output yet. Type /help for commands.{C.RESET}"))
        else:
            for persona, text in recent:
                color = PERSONA_COLORS.get(persona.lower(), C.WHITE)
                emoji = EMOJI.get(persona.lower(), "\U0001f41d")
                # Truncate long output and split lines
                text_lines = text.split("\n")
                header = f"{color}{emoji} [{persona.upper()}]{C.RESET}"
                lines.append(box_line(width, header))
                for tl in text_lines[:8]:
                    truncated = tl[:width - 6] if len(tl) > width - 6 else tl
                    lines.append(box_line(width, f"  {truncated}"))
                if len(text_lines) > 8:
                    lines.append(box_line(width, f"  {C.DIM}... ({len(text_lines) - 8} more lines){C.RESET}"))

        return lines

    def render_footer(self, width: int) -> list[str]:
        """Render the status footer."""
        lines = []
        lines.append(box_mid(width, "STATUS"))

        mem_stats = self.cli.memory.get_stats()
        db_stats = self.cli.db.get_stats()
        provider = os.environ.get("HIVE_PROVIDER", "gemini").lower()

        turns = mem_stats.get("total_turns", 0)
        sessions_count = db_stats.get("sessions_count", 0)
        rules_count = db_stats.get("rules_count", 0)

        footer = (
            f"{C.DIM}Turns:{C.RESET} {turns}  "
            f"{C.DIM}|{C.RESET}  "
            f"{C.DIM}Sessions:{C.RESET} {sessions_count}  "
            f"{C.DIM}|{C.RESET}  "
            f"{C.DIM}Rules:{C.RESET} {rules_count}  "
            f"{C.DIM}|{C.RESET}  "
            f"{C.DIM}Provider:{C.RESET} {C.GREEN}{provider}{C.RESET}  "
            f"{C.DIM}|{C.RESET}  "
            f"{C.DIM}Uptime:{C.RESET} {self.uptime()}"
        )
        lines.append(box_line(width, footer))
        lines.append(box_bottom(width))

        return lines

    def render_full(self, active_persona: str = "") -> str:
        """Render the complete HUD."""
        if not self.enabled:
            return ""
        width = min(_term_width(), 120)
        parts: list[str] = []
        parts.extend(self.render_header(width))
        parts.extend(self.render_persona_bar(width, active_persona))
        parts.extend(self.render_output(width))
        parts.extend(self.render_footer(width))
        return "\n".join(parts)

    def render_status_panel(self) -> str:
        """Render a detailed status panel for /status command."""
        width = min(_term_width(), 120)
        parts: list[str] = []

        parts.append(box_top(width, "SYSTEM STATUS"))

        # Provider info
        provider = os.environ.get("HIVE_PROVIDER", "gemini").lower()
        ladder = router.LADDERS.get(provider, {})
        parts.append(box_line(width, f"{C.BOLD}Provider:{C.RESET} {C.GREEN}{provider}{C.RESET}"))
        parts.append(box_line(width, f"  Tier 1 (Light):    {ladder.get(1, 'N/A')}"))
        parts.append(box_line(width, f"  Tier 2 (Standard): {ladder.get(2, 'N/A')}"))
        parts.append(box_line(width, f"  Tier 3 (Heavy):    {ladder.get(3, 'N/A')}"))
        parts.append(box_line(width, ""))

        # Available providers
        avail = ", ".join(router.LADDERS.keys())
        parts.append(box_line(width, f"{C.BOLD}Available:{C.RESET} {avail}"))
        parts.append(box_line(width, ""))

        # Persona status
        parts.append(box_line(width, f"{C.BOLD}Persona Status:{C.RESET}"))
        for p in PERSONA_NAMES:
            emoji = EMOJI.get(p, "?")
            color = PERSONA_COLORS.get(p, C.WHITE)
            status = self.persona_status.get(p, "idle")
            tier = router.TIER_MAP.get(p, 2)
            model = ladder.get(tier, "N/A")
            icon = self._status_icon(status)
            parts.append(box_line(width,
                f"  {color}{emoji} {p.capitalize():10s}{C.RESET} "
                f"Status: {icon} {status:8s}  "
                f"Tier: {tier}  Model: {C.DIM}{model}{C.RESET}"
            ))
        parts.append(box_line(width, ""))

        # Memory stats
        mem_stats = self.cli.memory.get_stats()
        db_stats = self.cli.db.get_stats()
        parts.append(box_line(width, f"{C.BOLD}Memory:{C.RESET}"))
        parts.append(box_line(width, f"  Working turns:      {mem_stats.get('working_size', 0)}"))
        parts.append(box_line(width, f"  Compressed anchors: {mem_stats.get('compressed_anchors', 0)}"))
        parts.append(box_line(width, f"  Archival turns:     {mem_stats.get('archival_size', 0)}"))
        parts.append(box_line(width, f"  Total turns (RAM):  {mem_stats.get('total_turns', 0)}"))
        parts.append(box_line(width, ""))
        parts.append(box_line(width, f"{C.BOLD}Database:{C.RESET}"))
        for k, v in db_stats.items():
            parts.append(box_line(width, f"  {k}: {v}"))
        parts.append(box_line(width, ""))

        # Session info
        parts.append(box_line(width, f"{C.BOLD}Session:{C.RESET} {self.cli.session_id}"))
        parts.append(box_line(width, f"{C.BOLD}Uptime:{C.RESET}  {self.uptime()}"))

        parts.append(box_bottom(width))
        return "\n".join(parts)


# ─── Main CLI Class ───────────────────────────────────────────────
class HiveCLI:
    """Main CLI controller with rich HUD."""

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

        self.hud = HUD(self)
        self._active_persona = ""

    def _print(self, persona: str, message: str) -> None:
        """Print persona output with color coding."""
        color = PERSONA_COLORS.get(persona.lower(), C.WHITE)
        emoji = EMOJI.get(persona, "\U0001f41d")
        header = f"\n{color}{emoji} [{persona.upper()}]{C.RESET}"
        print(f"{header}: {message}")
        self.hud.add_output(persona, message)

    def _save_turn(self, role: str, content: str, persona: str) -> None:
        self.memory.add_turn(role, content, persona)
        self.db.save_turn(self.session_id, role, content, persona)

    def _show_hud(self) -> None:
        """Display the HUD if enabled."""
        if self.hud.enabled:
            print(self.hud.render_full(self._active_persona))

    async def _handle_run(self, task: str) -> None:
        """Run full pipeline with step-by-step progress."""
        self._print("pipeline", f"Running full pipeline for: {task[:80]}...")
        self._save_turn("user", task, "pipeline")

        width = min(_term_width(), 120)
        steps = [
            {"index": 1, "total": 4, "persona": "Oracle", "status": "pending", "elapsed": 0.0, "parallel": False},
            {"index": 2, "total": 4, "persona": "Forge", "status": "pending", "elapsed": 0.0, "parallel": False},
            {"index": 3, "total": 4, "persona": "Sentinel", "status": "pending", "elapsed": 0.0, "parallel": True},
            {"index": 4, "total": 4, "persona": "Aegis", "status": "pending", "elapsed": 0.0, "parallel": True},
        ]

        def _show_progress() -> None:
            if self.hud.enabled:
                progress_lines = self.hud.render_pipeline_progress(width, steps)
                print("\n".join(progress_lines))

        # Step 1: Oracle
        steps[0]["status"] = "working"
        self.hud.set_persona_status("oracle", "working")
        self._active_persona = "oracle"
        _show_progress()

        t0 = time.time()
        result = await self.pipeline.run(task)
        # We ran the whole pipeline; compute approximate timings
        total_time = time.time() - t0

        # Mark all done
        per_step = total_time / 4
        for i, s in enumerate(steps):
            s["status"] = "done"
            s["elapsed"] = per_step * (i + 1)

        self.hud.set_persona_status("oracle", "done")
        self.hud.set_persona_status("forge", "done")
        self.hud.set_persona_status("sentinel", "done")
        self.hud.set_persona_status("aegis", "done")

        _show_progress()

        self._print("oracle", f"Plan:\n{result.plan[:500]}")
        self._print("forge", f"Code:\n{result.code[:500]}")
        self._print("sentinel", f"Security Review:\n{result.security_review[:500]}")
        self._print("aegis", f"Red Team Review:\n{result.red_team_review[:500]}")

        if not result.success:
            self._print("pipeline", f"Errors: {', '.join(result.errors)}")
            for s in steps:
                if s["persona"].lower() in [e.split()[0].lower() for e in result.errors]:
                    s["status"] = "error"

        self._save_turn("assistant", json.dumps({
            "plan": result.plan[:200],
            "success": result.success,
        }), "pipeline")

        # Reset persona statuses
        for p in PERSONA_NAMES:
            self.hud.set_persona_status(p, "idle")
        self._active_persona = ""

    async def _handle_forge(self, prompt: str) -> None:
        self._active_persona = "forge"
        self.hud.set_persona_status("forge", "working")
        self._save_turn("user", prompt, "forge")
        try:
            result = self.forge.process(prompt)
            self.hud.set_persona_status("forge", "done")
            self._print("forge", result)
            self._save_turn("assistant", result, "forge")
        except Exception as e:
            self.hud.set_persona_status("forge", "error")
            self._print("forge", f"Error: {e}")
        finally:
            self.hud.set_persona_status("forge", "idle")
            self._active_persona = ""

    async def _handle_oracle(self, prompt: str) -> None:
        self._active_persona = "oracle"
        self.hud.set_persona_status("oracle", "working")
        self._save_turn("user", prompt, "oracle")
        try:
            result = self.oracle.process(prompt)
            self.hud.set_persona_status("oracle", "done")
            self._print("oracle", json.dumps(result, indent=2))
            self._save_turn("assistant", json.dumps(result), "oracle")
        except Exception as e:
            self.hud.set_persona_status("oracle", "error")
            self._print("oracle", f"Error: {e}")
        finally:
            self.hud.set_persona_status("oracle", "idle")
            self._active_persona = ""

    async def _handle_sentinel(self, content: str) -> None:
        self._active_persona = "sentinel"
        self.hud.set_persona_status("sentinel", "working")
        self._save_turn("user", content[:200], "sentinel")
        try:
            result = self.sentinel.process(content)
            self.hud.set_persona_status("sentinel", "done")
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
            self.hud.set_persona_status("sentinel", "error")
            self._print("sentinel", f"Error: {e}")
        finally:
            self.hud.set_persona_status("sentinel", "idle")
            self._active_persona = ""

    async def _handle_heal(self, target: str) -> None:
        self._active_persona = "debug"
        self.hud.set_persona_status("debug", "working")
        self._save_turn("user", target, "debug")
        try:
            result = self.debug.process(target)
            self.hud.set_persona_status("debug", "done")
            status = "SUCCESS" if result.success else "FAILED"
            output = f"Status: {status} ({len(result.attempts)} attempts)"
            if result.final_error:
                output += f"\nFinal error: {result.final_error}"
            if result.final_code:
                output += f"\nFinal code:\n{result.final_code[:500]}"
            self._print("debug", output)
            self._save_turn("assistant", output, "debug")
        except Exception as e:
            self.hud.set_persona_status("debug", "error")
            self._print("debug", f"Error: {e}")
        finally:
            self.hud.set_persona_status("debug", "idle")
            self._active_persona = ""

    async def _handle_muse(self, prompt: str) -> None:
        self._active_persona = "muse"
        self.hud.set_persona_status("muse", "working")
        self._save_turn("user", prompt, "muse")
        try:
            result = self.muse.process(prompt)
            self.hud.set_persona_status("muse", "done")
            output = (
                f"PRECISE:\n{result.precise}\n\n"
                f"CONSTRAINED:\n{result.constrained}\n\n"
                f"CREATIVE:\n{result.creative}"
            )
            self._print("muse", output)
            self._save_turn("assistant", output, "muse")
        except Exception as e:
            self.hud.set_persona_status("muse", "error")
            self._print("muse", f"Error: {e}")
        finally:
            self.hud.set_persona_status("muse", "idle")
            self._active_persona = ""

    async def _handle_compress(self, text: str) -> None:
        self._active_persona = "coda"
        self.hud.set_persona_status("coda", "working")
        self._save_turn("user", text[:200], "coda")
        try:
            result = self.coda.process(text)
            self.hud.set_persona_status("coda", "done")
            output = (
                f"Summary: {result.summary}\n"
                f"Key Decisions: {', '.join(result.key_decisions) or 'none'}\n"
                f"Constraints: {', '.join(result.constraints) or 'none'}\n"
                f"Assertions: {', '.join(result.assertions) or 'none'}"
            )
            self._print("coda", output)
            self._save_turn("assistant", output, "coda")
        except Exception as e:
            self.hud.set_persona_status("coda", "error")
            self._print("coda", f"Error: {e}")
        finally:
            self.hud.set_persona_status("coda", "idle")
            self._active_persona = ""

    async def _handle_aegis(self, content: str) -> None:
        self._active_persona = "aegis"
        self.hud.set_persona_status("aegis", "working")
        self._save_turn("user", content[:200], "aegis")
        try:
            result = self.aegis.process(content)
            self.hud.set_persona_status("aegis", "done")
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
            self.hud.set_persona_status("aegis", "error")
            self._print("aegis", f"Error: {e}")
        finally:
            self.hud.set_persona_status("aegis", "idle")
            self._active_persona = ""

    async def _handle_apis(self, url: str) -> None:
        self._active_persona = "apis"
        self.hud.set_persona_status("apis", "working")
        self._save_turn("user", url, "apis")
        try:
            result = self.apis.process(url)
            self.hud.set_persona_status("apis", "done")
            self._print("apis", result)
            self._save_turn("assistant", result, "apis")
        except Exception as e:
            self.hud.set_persona_status("apis", "error")
            self._print("apis", f"Error: {e}")
        finally:
            self.hud.set_persona_status("apis", "idle")
            self._active_persona = ""

    # ── Forge skill handlers ────────────────────────────────────────

    async def _handle_refactor(self, arg: str) -> None:
        self._active_persona = "forge"
        self.hud.set_persona_status("forge", "working")
        self._save_turn("user", arg, "forge")
        try:
            result = self.forge.refactor(arg)
            self.hud.set_persona_status("forge", "done")
            self._print("forge", result)
            self._save_turn("assistant", result, "forge")
        except Exception as e:
            self.hud.set_persona_status("forge", "error")
            self._print("forge", f"Error: {e}")
        finally:
            self.hud.set_persona_status("forge", "idle")
            self._active_persona = ""

    async def _handle_tests(self, arg: str) -> None:
        self._active_persona = "forge"
        self.hud.set_persona_status("forge", "working")
        self._save_turn("user", arg, "forge")
        try:
            result = self.forge.add_tests(arg)
            self.hud.set_persona_status("forge", "done")
            self._print("forge", result)
            self._save_turn("assistant", result, "forge")
        except Exception as e:
            self.hud.set_persona_status("forge", "error")
            self._print("forge", f"Error: {e}")
        finally:
            self.hud.set_persona_status("forge", "idle")
            self._active_persona = ""

    async def _handle_convert(self, arg: str) -> None:
        self._active_persona = "forge"
        self.hud.set_persona_status("forge", "working")
        self._save_turn("user", arg, "forge")
        try:
            parts = arg.split(None, 1)
            target_language = parts[0] if parts else ""
            code = parts[1] if len(parts) > 1 else ""
            result = self.forge.convert(target_language, code)
            self.hud.set_persona_status("forge", "done")
            self._print("forge", result)
            self._save_turn("assistant", result, "forge")
        except Exception as e:
            self.hud.set_persona_status("forge", "error")
            self._print("forge", f"Error: {e}")
        finally:
            self.hud.set_persona_status("forge", "idle")
            self._active_persona = ""

    async def _handle_document(self, arg: str) -> None:
        self._active_persona = "forge"
        self.hud.set_persona_status("forge", "working")
        self._save_turn("user", arg, "forge")
        try:
            result = self.forge.document(arg)
            self.hud.set_persona_status("forge", "done")
            self._print("forge", result)
            self._save_turn("assistant", result, "forge")
        except Exception as e:
            self.hud.set_persona_status("forge", "error")
            self._print("forge", f"Error: {e}")
        finally:
            self.hud.set_persona_status("forge", "idle")
            self._active_persona = ""

    # ── Oracle skill handlers ────────────────────────────────────────

    async def _handle_deps(self, arg: str) -> None:
        self._active_persona = "oracle"
        self.hud.set_persona_status("oracle", "working")
        self._save_turn("user", arg, "oracle")
        try:
            result = self.oracle.dependency_analysis(arg)
            self.hud.set_persona_status("oracle", "done")
            output = json.dumps(result, indent=2)
            self._print("oracle", output)
            self._save_turn("assistant", output, "oracle")
        except Exception as e:
            self.hud.set_persona_status("oracle", "error")
            self._print("oracle", f"Error: {e}")
        finally:
            self.hud.set_persona_status("oracle", "idle")
            self._active_persona = ""

    async def _handle_diagram(self, arg: str) -> None:
        self._active_persona = "oracle"
        self.hud.set_persona_status("oracle", "working")
        self._save_turn("user", arg, "oracle")
        try:
            result = self.oracle.architecture_diagram(arg)
            self.hud.set_persona_status("oracle", "done")
            output = json.dumps(result, indent=2)
            self._print("oracle", output)
            self._save_turn("assistant", output, "oracle")
        except Exception as e:
            self.hud.set_persona_status("oracle", "error")
            self._print("oracle", f"Error: {e}")
        finally:
            self.hud.set_persona_status("oracle", "idle")
            self._active_persona = ""

    async def _handle_estimate(self, arg: str) -> None:
        self._active_persona = "oracle"
        self.hud.set_persona_status("oracle", "working")
        self._save_turn("user", arg, "oracle")
        try:
            result = self.oracle.estimate_effort(arg)
            self.hud.set_persona_status("oracle", "done")
            output = json.dumps(result, indent=2)
            self._print("oracle", output)
            self._save_turn("assistant", output, "oracle")
        except Exception as e:
            self.hud.set_persona_status("oracle", "error")
            self._print("oracle", f"Error: {e}")
        finally:
            self.hud.set_persona_status("oracle", "idle")
            self._active_persona = ""

    # ── Sentinel skill handlers ──────────────────────────────────────

    async def _handle_scandeps(self, arg: str) -> None:
        self._active_persona = "sentinel"
        self.hud.set_persona_status("sentinel", "working")
        self._save_turn("user", arg, "sentinel")
        try:
            result = self.sentinel.scan_dependencies(arg)
            self.hud.set_persona_status("sentinel", "done")
            output = json.dumps(result, indent=2)
            self._print("sentinel", output)
            self._save_turn("assistant", output, "sentinel")
        except Exception as e:
            self.hud.set_persona_status("sentinel", "error")
            self._print("sentinel", f"Error: {e}")
        finally:
            self.hud.set_persona_status("sentinel", "idle")
            self._active_persona = ""

    async def _handle_owasp(self, arg: str) -> None:
        self._active_persona = "sentinel"
        self.hud.set_persona_status("sentinel", "working")
        self._save_turn("user", arg, "sentinel")
        try:
            result = self.sentinel.owasp_checklist(arg)
            self.hud.set_persona_status("sentinel", "done")
            output = json.dumps(result, indent=2)
            self._print("sentinel", output)
            self._save_turn("assistant", output, "sentinel")
        except Exception as e:
            self.hud.set_persona_status("sentinel", "error")
            self._print("sentinel", f"Error: {e}")
        finally:
            self.hud.set_persona_status("sentinel", "idle")
            self._active_persona = ""

    async def _handle_compliance(self, arg: str) -> None:
        self._active_persona = "sentinel"
        self.hud.set_persona_status("sentinel", "working")
        self._save_turn("user", arg, "sentinel")
        try:
            result = self.sentinel.compliance_check(arg)
            self.hud.set_persona_status("sentinel", "done")
            output = json.dumps(result, indent=2)
            self._print("sentinel", output)
            self._save_turn("assistant", output, "sentinel")
        except Exception as e:
            self.hud.set_persona_status("sentinel", "error")
            self._print("sentinel", f"Error: {e}")
        finally:
            self.hud.set_persona_status("sentinel", "idle")
            self._active_persona = ""

    # ── Debug skill handlers ─────────────────────────────────────────

    async def _handle_profile(self, arg: str) -> None:
        self._active_persona = "debug"
        self.hud.set_persona_status("debug", "working")
        self._save_turn("user", arg, "debug")
        try:
            result = self.debug.profile_performance(arg)
            self.hud.set_persona_status("debug", "done")
            self._print("debug", result)
            self._save_turn("assistant", result, "debug")
        except Exception as e:
            self.hud.set_persona_status("debug", "error")
            self._print("debug", f"Error: {e}")
        finally:
            self.hud.set_persona_status("debug", "idle")
            self._active_persona = ""

    async def _handle_trace(self, arg: str) -> None:
        self._active_persona = "debug"
        self.hud.set_persona_status("debug", "working")
        self._save_turn("user", arg, "debug")
        try:
            result = self.debug.trace_error(arg)
            self.hud.set_persona_status("debug", "done")
            self._print("debug", result)
            self._save_turn("assistant", result, "debug")
        except Exception as e:
            self.hud.set_persona_status("debug", "error")
            self._print("debug", f"Error: {e}")
        finally:
            self.hud.set_persona_status("debug", "idle")
            self._active_persona = ""

    async def _handle_stacktrace(self, arg: str) -> None:
        self._active_persona = "debug"
        self.hud.set_persona_status("debug", "working")
        self._save_turn("user", arg, "debug")
        try:
            result = self.debug.explain_stacktrace(arg)
            self.hud.set_persona_status("debug", "done")
            self._print("debug", result)
            self._save_turn("assistant", result, "debug")
        except Exception as e:
            self.hud.set_persona_status("debug", "error")
            self._print("debug", f"Error: {e}")
        finally:
            self.hud.set_persona_status("debug", "idle")
            self._active_persona = ""

    # ── Muse skill handlers ──────────────────────────────────────────

    async def _handle_mockup(self, arg: str) -> None:
        self._active_persona = "muse"
        self.hud.set_persona_status("muse", "working")
        self._save_turn("user", arg, "muse")
        try:
            result = self.muse.ui_mockup(arg)
            self.hud.set_persona_status("muse", "done")
            self._print("muse", result)
            self._save_turn("assistant", result, "muse")
        except Exception as e:
            self.hud.set_persona_status("muse", "error")
            self._print("muse", f"Error: {e}")
        finally:
            self.hud.set_persona_status("muse", "idle")
            self._active_persona = ""

    async def _handle_naming(self, arg: str) -> None:
        self._active_persona = "muse"
        self.hud.set_persona_status("muse", "working")
        self._save_turn("user", arg, "muse")
        try:
            result = self.muse.naming_suggestions(arg)
            self.hud.set_persona_status("muse", "done")
            self._print("muse", result)
            self._save_turn("assistant", result, "muse")
        except Exception as e:
            self.hud.set_persona_status("muse", "error")
            self._print("muse", f"Error: {e}")
        finally:
            self.hud.set_persona_status("muse", "idle")
            self._active_persona = ""

    async def _handle_brainstorm(self, arg: str) -> None:
        self._active_persona = "muse"
        self.hud.set_persona_status("muse", "working")
        self._save_turn("user", arg, "muse")
        try:
            result = self.muse.brainstorm(arg)
            self.hud.set_persona_status("muse", "done")
            self._print("muse", result)
            self._save_turn("assistant", result, "muse")
        except Exception as e:
            self.hud.set_persona_status("muse", "error")
            self._print("muse", f"Error: {e}")
        finally:
            self.hud.set_persona_status("muse", "idle")
            self._active_persona = ""

    # ── Coda skill handlers ──────────────────────────────────────────

    async def _handle_changelog(self, arg: str) -> None:
        self._active_persona = "coda"
        self.hud.set_persona_status("coda", "working")
        self._save_turn("user", arg, "coda")
        try:
            result = self.coda.changelog(arg)
            self.hud.set_persona_status("coda", "done")
            output = json.dumps(dataclasses.asdict(result), indent=2)
            self._print("coda", output)
            self._save_turn("assistant", output, "coda")
        except Exception as e:
            self.hud.set_persona_status("coda", "error")
            self._print("coda", f"Error: {e}")
        finally:
            self.hud.set_persona_status("coda", "idle")
            self._active_persona = ""

    async def _handle_diff(self, arg: str) -> None:
        self._active_persona = "coda"
        self.hud.set_persona_status("coda", "working")
        self._save_turn("user", arg, "coda")
        try:
            result = self.coda.diff_summary(arg)
            self.hud.set_persona_status("coda", "done")
            output = json.dumps(dataclasses.asdict(result), indent=2)
            self._print("coda", output)
            self._save_turn("assistant", output, "coda")
        except Exception as e:
            self.hud.set_persona_status("coda", "error")
            self._print("coda", f"Error: {e}")
        finally:
            self.hud.set_persona_status("coda", "idle")
            self._active_persona = ""

    async def _handle_meeting(self, arg: str) -> None:
        self._active_persona = "coda"
        self.hud.set_persona_status("coda", "working")
        self._save_turn("user", arg, "coda")
        try:
            result = self.coda.meeting_notes(arg)
            self.hud.set_persona_status("coda", "done")
            output = json.dumps(dataclasses.asdict(result), indent=2)
            self._print("coda", output)
            self._save_turn("assistant", output, "coda")
        except Exception as e:
            self.hud.set_persona_status("coda", "error")
            self._print("coda", f"Error: {e}")
        finally:
            self.hud.set_persona_status("coda", "idle")
            self._active_persona = ""

    # ── Aegis skill handlers ─────────────────────────────────────────

    async def _handle_threat(self, arg: str) -> None:
        self._active_persona = "aegis"
        self.hud.set_persona_status("aegis", "working")
        self._save_turn("user", arg, "aegis")
        try:
            result = self.aegis.threat_model(arg)
            self.hud.set_persona_status("aegis", "done")
            output = json.dumps(result, indent=2)
            self._print("aegis", output)
            self._save_turn("assistant", output, "aegis")
        except Exception as e:
            self.hud.set_persona_status("aegis", "error")
            self._print("aegis", f"Error: {e}")
        finally:
            self.hud.set_persona_status("aegis", "idle")
            self._active_persona = ""

    async def _handle_fuzz(self, arg: str) -> None:
        self._active_persona = "aegis"
        self.hud.set_persona_status("aegis", "working")
        self._save_turn("user", arg, "aegis")
        try:
            result = self.aegis.fuzz_inputs(arg)
            self.hud.set_persona_status("aegis", "done")
            output = json.dumps(result, indent=2)
            self._print("aegis", output)
            self._save_turn("assistant", output, "aegis")
        except Exception as e:
            self.hud.set_persona_status("aegis", "error")
            self._print("aegis", f"Error: {e}")
        finally:
            self.hud.set_persona_status("aegis", "idle")
            self._active_persona = ""

    async def _handle_surface(self, arg: str) -> None:
        self._active_persona = "aegis"
        self.hud.set_persona_status("aegis", "working")
        self._save_turn("user", arg, "aegis")
        try:
            result = self.aegis.attack_surface_map(arg)
            self.hud.set_persona_status("aegis", "done")
            output = json.dumps(result, indent=2)
            self._print("aegis", output)
            self._save_turn("assistant", output, "aegis")
        except Exception as e:
            self.hud.set_persona_status("aegis", "error")
            self._print("aegis", f"Error: {e}")
        finally:
            self.hud.set_persona_status("aegis", "idle")
            self._active_persona = ""

    # ── Apis skill handlers ──────────────────────────────────────────

    async def _handle_contract(self, arg: str) -> None:
        self._active_persona = "apis"
        self.hud.set_persona_status("apis", "working")
        self._save_turn("user", arg, "apis")
        try:
            result = self.apis.validate_contract(arg)
            self.hud.set_persona_status("apis", "done")
            output = json.dumps(result, indent=2)
            self._print("apis", output)
            self._save_turn("assistant", output, "apis")
        except Exception as e:
            self.hud.set_persona_status("apis", "error")
            self._print("apis", f"Error: {e}")
        finally:
            self.hud.set_persona_status("apis", "idle")
            self._active_persona = ""

    async def _handle_loadtest(self, arg: str) -> None:
        self._active_persona = "apis"
        self.hud.set_persona_status("apis", "working")
        self._save_turn("user", arg, "apis")
        try:
            result = self.apis.load_test(arg)
            self.hud.set_persona_status("apis", "done")
            output = json.dumps(result, indent=2)
            self._print("apis", output)
            self._save_turn("assistant", output, "apis")
        except Exception as e:
            self.hud.set_persona_status("apis", "error")
            self._print("apis", f"Error: {e}")
        finally:
            self.hud.set_persona_status("apis", "idle")
            self._active_persona = ""

    async def _handle_mockserver(self, arg: str) -> None:
        self._active_persona = "apis"
        self.hud.set_persona_status("apis", "working")
        self._save_turn("user", arg, "apis")
        try:
            result = self.apis.mock_server(arg)
            self.hud.set_persona_status("apis", "done")
            output = json.dumps(result, indent=2)
            self._print("apis", output)
            self._save_turn("assistant", output, "apis")
        except Exception as e:
            self.hud.set_persona_status("apis", "error")
            self._print("apis", f"Error: {e}")
        finally:
            self.hud.set_persona_status("apis", "idle")
            self._active_persona = ""

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

    async def _handle_provider(self, name: str) -> None:
        """Switch the active provider."""
        name = name.strip().lower()
        if name not in router.LADDERS:
            available = ", ".join(router.LADDERS.keys())
            self._print("hive", f"Unknown provider '{name}'. Available: {available}")
            return
        os.environ["HIVE_PROVIDER"] = name
        ladder = router.LADDERS[name]
        self._print("hive",
            f"Switched to provider: {C.GREEN}{name}{C.RESET}\n"
            f"  Tier 1: {ladder.get(1, 'N/A')}\n"
            f"  Tier 2: {ladder.get(2, 'N/A')}\n"
            f"  Tier 3: {ladder.get(3, 'N/A')}"
        )

    async def _handle_status(self) -> None:
        """Show the full system status panel."""
        print(self.hud.render_status_panel())

    async def _handle_hud(self) -> None:
        """Toggle HUD on/off."""
        enabled = self.hud.toggle()
        state = f"{C.GREEN}ON{C.RESET}" if enabled else f"{C.RED}OFF{C.RESET}"
        self._print("hive", f"HUD display: {state}")

    # ── Forge extended skills ──

    async def _handle_refactor(self, arg: str) -> None:
        self._active_persona = "forge"
        self.hud.set_persona_status("forge", "working")
        self._save_turn("user", arg, "forge")
        try:
            result = self.forge.refactor(arg)
            self.hud.set_persona_status("forge", "done")
            self._print("forge", result)
            self._save_turn("assistant", result, "forge")
        except Exception as e:
            self.hud.set_persona_status("forge", "error")
            self._print("forge", f"Error: {e}")
        finally:
            self.hud.set_persona_status("forge", "idle")
            self._active_persona = ""

    async def _handle_tests(self, arg: str) -> None:
        self._active_persona = "forge"
        self.hud.set_persona_status("forge", "working")
        self._save_turn("user", arg, "forge")
        try:
            result = self.forge.add_tests(arg)
            self.hud.set_persona_status("forge", "done")
            self._print("forge", result)
            self._save_turn("assistant", result, "forge")
        except Exception as e:
            self.hud.set_persona_status("forge", "error")
            self._print("forge", f"Error: {e}")
        finally:
            self.hud.set_persona_status("forge", "idle")
            self._active_persona = ""

    async def _handle_convert(self, arg: str) -> None:
        parts = arg.split(None, 1)
        if len(parts) < 2:
            self._print("forge", "Usage: /convert <language> <code>")
            return
        target_lang, code = parts[0], parts[1]
        self._active_persona = "forge"
        self.hud.set_persona_status("forge", "working")
        self._save_turn("user", arg, "forge")
        try:
            result = self.forge.convert_language(code, target_lang)
            self.hud.set_persona_status("forge", "done")
            self._print("forge", result)
            self._save_turn("assistant", result, "forge")
        except Exception as e:
            self.hud.set_persona_status("forge", "error")
            self._print("forge", f"Error: {e}")
        finally:
            self.hud.set_persona_status("forge", "idle")
            self._active_persona = ""

    async def _handle_document(self, arg: str) -> None:
        self._active_persona = "forge"
        self.hud.set_persona_status("forge", "working")
        self._save_turn("user", arg, "forge")
        try:
            result = self.forge.document(arg)
            self.hud.set_persona_status("forge", "done")
            self._print("forge", result)
            self._save_turn("assistant", result, "forge")
        except Exception as e:
            self.hud.set_persona_status("forge", "error")
            self._print("forge", f"Error: {e}")
        finally:
            self.hud.set_persona_status("forge", "idle")
            self._active_persona = ""

    # ── Oracle extended skills ──

    async def _handle_deps(self, arg: str) -> None:
        self._active_persona = "oracle"
        self.hud.set_persona_status("oracle", "working")
        self._save_turn("user", arg, "oracle")
        try:
            result = self.oracle.dependency_analysis(arg)
            self.hud.set_persona_status("oracle", "done")
            self._print("oracle", json.dumps(result, indent=2))
            self._save_turn("assistant", json.dumps(result), "oracle")
        except Exception as e:
            self.hud.set_persona_status("oracle", "error")
            self._print("oracle", f"Error: {e}")
        finally:
            self.hud.set_persona_status("oracle", "idle")
            self._active_persona = ""

    async def _handle_diagram(self, arg: str) -> None:
        self._active_persona = "oracle"
        self.hud.set_persona_status("oracle", "working")
        self._save_turn("user", arg, "oracle")
        try:
            result = self.oracle.architecture_diagram(arg)
            self.hud.set_persona_status("oracle", "done")
            self._print("oracle", result)
            self._save_turn("assistant", result, "oracle")
        except Exception as e:
            self.hud.set_persona_status("oracle", "error")
            self._print("oracle", f"Error: {e}")
        finally:
            self.hud.set_persona_status("oracle", "idle")
            self._active_persona = ""

    async def _handle_estimate(self, arg: str) -> None:
        self._active_persona = "oracle"
        self.hud.set_persona_status("oracle", "working")
        self._save_turn("user", arg, "oracle")
        try:
            result = self.oracle.estimate_effort(arg)
            self.hud.set_persona_status("oracle", "done")
            self._print("oracle", json.dumps(result, indent=2))
            self._save_turn("assistant", json.dumps(result), "oracle")
        except Exception as e:
            self.hud.set_persona_status("oracle", "error")
            self._print("oracle", f"Error: {e}")
        finally:
            self.hud.set_persona_status("oracle", "idle")
            self._active_persona = ""

    # ── Sentinel extended skills ──

    async def _handle_scandeps(self, arg: str) -> None:
        self._active_persona = "sentinel"
        self.hud.set_persona_status("sentinel", "working")
        self._save_turn("user", arg[:200], "sentinel")
        try:
            result = self.sentinel.scan_dependencies(arg)
            self.hud.set_persona_status("sentinel", "done")
            self._print("sentinel", json.dumps(result, indent=2))
            self._save_turn("assistant", json.dumps(result), "sentinel")
        except Exception as e:
            self.hud.set_persona_status("sentinel", "error")
            self._print("sentinel", f"Error: {e}")
        finally:
            self.hud.set_persona_status("sentinel", "idle")
            self._active_persona = ""

    async def _handle_owasp(self, arg: str) -> None:
        self._active_persona = "sentinel"
        self.hud.set_persona_status("sentinel", "working")
        self._save_turn("user", arg[:200], "sentinel")
        try:
            result = self.sentinel.owasp_checklist(arg)
            self.hud.set_persona_status("sentinel", "done")
            self._print("sentinel", json.dumps(result, indent=2))
            self._save_turn("assistant", json.dumps(result), "sentinel")
        except Exception as e:
            self.hud.set_persona_status("sentinel", "error")
            self._print("sentinel", f"Error: {e}")
        finally:
            self.hud.set_persona_status("sentinel", "idle")
            self._active_persona = ""

    async def _handle_compliance(self, arg: str) -> None:
        self._active_persona = "sentinel"
        self.hud.set_persona_status("sentinel", "working")
        self._save_turn("user", arg[:200], "sentinel")
        try:
            result = self.sentinel.compliance_check(arg)
            self.hud.set_persona_status("sentinel", "done")
            self._print("sentinel", json.dumps(result, indent=2))
            self._save_turn("assistant", json.dumps(result), "sentinel")
        except Exception as e:
            self.hud.set_persona_status("sentinel", "error")
            self._print("sentinel", f"Error: {e}")
        finally:
            self.hud.set_persona_status("sentinel", "idle")
            self._active_persona = ""

    # ── Debug extended skills ──

    async def _handle_profile(self, arg: str) -> None:
        self._active_persona = "debug"
        self.hud.set_persona_status("debug", "working")
        self._save_turn("user", arg, "debug")
        try:
            result = self.debug.profile_performance(arg)
            self.hud.set_persona_status("debug", "done")
            self._print("debug", json.dumps(result, indent=2))
            self._save_turn("assistant", json.dumps(result), "debug")
        except Exception as e:
            self.hud.set_persona_status("debug", "error")
            self._print("debug", f"Error: {e}")
        finally:
            self.hud.set_persona_status("debug", "idle")
            self._active_persona = ""

    async def _handle_trace(self, arg: str) -> None:
        self._active_persona = "debug"
        self.hud.set_persona_status("debug", "working")
        self._save_turn("user", arg, "debug")
        try:
            result = self.debug.trace_error(arg)
            self.hud.set_persona_status("debug", "done")
            self._print("debug", json.dumps(result, indent=2))
            self._save_turn("assistant", json.dumps(result), "debug")
        except Exception as e:
            self.hud.set_persona_status("debug", "error")
            self._print("debug", f"Error: {e}")
        finally:
            self.hud.set_persona_status("debug", "idle")
            self._active_persona = ""

    async def _handle_stacktrace(self, arg: str) -> None:
        self._active_persona = "debug"
        self.hud.set_persona_status("debug", "working")
        self._save_turn("user", arg, "debug")
        try:
            result = self.debug.explain_stacktrace(arg)
            self.hud.set_persona_status("debug", "done")
            self._print("debug", json.dumps(result, indent=2))
            self._save_turn("assistant", json.dumps(result), "debug")
        except Exception as e:
            self.hud.set_persona_status("debug", "error")
            self._print("debug", f"Error: {e}")
        finally:
            self.hud.set_persona_status("debug", "idle")
            self._active_persona = ""

    # ── Muse extended skills ──

    async def _handle_mockup(self, arg: str) -> None:
        self._active_persona = "muse"
        self.hud.set_persona_status("muse", "working")
        self._save_turn("user", arg, "muse")
        try:
            result = self.muse.ui_mockup(arg)
            self.hud.set_persona_status("muse", "done")
            self._print("muse", result)
            self._save_turn("assistant", result, "muse")
        except Exception as e:
            self.hud.set_persona_status("muse", "error")
            self._print("muse", f"Error: {e}")
        finally:
            self.hud.set_persona_status("muse", "idle")
            self._active_persona = ""

    async def _handle_naming(self, arg: str) -> None:
        self._active_persona = "muse"
        self.hud.set_persona_status("muse", "working")
        self._save_turn("user", arg, "muse")
        try:
            result = self.muse.naming_suggestions(arg)
            self.hud.set_persona_status("muse", "done")
            self._print("muse", json.dumps(result, indent=2))
            self._save_turn("assistant", json.dumps(result), "muse")
        except Exception as e:
            self.hud.set_persona_status("muse", "error")
            self._print("muse", f"Error: {e}")
        finally:
            self.hud.set_persona_status("muse", "idle")
            self._active_persona = ""

    async def _handle_brainstorm(self, arg: str) -> None:
        self._active_persona = "muse"
        self.hud.set_persona_status("muse", "working")
        self._save_turn("user", arg, "muse")
        try:
            result = self.muse.brainstorm(arg)
            self.hud.set_persona_status("muse", "done")
            self._print("muse", json.dumps(result, indent=2))
            self._save_turn("assistant", json.dumps(result), "muse")
        except Exception as e:
            self.hud.set_persona_status("muse", "error")
            self._print("muse", f"Error: {e}")
        finally:
            self.hud.set_persona_status("muse", "idle")
            self._active_persona = ""

    # ── Coda extended skills ──

    async def _handle_changelog(self, arg: str) -> None:
        self._active_persona = "coda"
        self.hud.set_persona_status("coda", "working")
        self._save_turn("user", arg[:200], "coda")
        try:
            result = self.coda.changelog(arg)
            self.hud.set_persona_status("coda", "done")
            import dataclasses
            output = json.dumps(dataclasses.asdict(result), indent=2)
            self._print("coda", output)
            self._save_turn("assistant", output, "coda")
        except Exception as e:
            self.hud.set_persona_status("coda", "error")
            self._print("coda", f"Error: {e}")
        finally:
            self.hud.set_persona_status("coda", "idle")
            self._active_persona = ""

    async def _handle_diff(self, arg: str) -> None:
        self._active_persona = "coda"
        self.hud.set_persona_status("coda", "working")
        self._save_turn("user", arg[:200], "coda")
        try:
            result = self.coda.diff_summary(arg)
            self.hud.set_persona_status("coda", "done")
            import dataclasses
            output = json.dumps(dataclasses.asdict(result), indent=2)
            self._print("coda", output)
            self._save_turn("assistant", output, "coda")
        except Exception as e:
            self.hud.set_persona_status("coda", "error")
            self._print("coda", f"Error: {e}")
        finally:
            self.hud.set_persona_status("coda", "idle")
            self._active_persona = ""

    async def _handle_meeting(self, arg: str) -> None:
        self._active_persona = "coda"
        self.hud.set_persona_status("coda", "working")
        self._save_turn("user", arg[:200], "coda")
        try:
            result = self.coda.meeting_notes(arg)
            self.hud.set_persona_status("coda", "done")
            import dataclasses
            output = json.dumps(dataclasses.asdict(result), indent=2)
            self._print("coda", output)
            self._save_turn("assistant", output, "coda")
        except Exception as e:
            self.hud.set_persona_status("coda", "error")
            self._print("coda", f"Error: {e}")
        finally:
            self.hud.set_persona_status("coda", "idle")
            self._active_persona = ""

    # ── Aegis extended skills ──

    async def _handle_threat(self, arg: str) -> None:
        self._active_persona = "aegis"
        self.hud.set_persona_status("aegis", "working")
        self._save_turn("user", arg[:200], "aegis")
        try:
            result = self.aegis.threat_model(arg)
            self.hud.set_persona_status("aegis", "done")
            self._print("aegis", json.dumps(result, indent=2))
            self._save_turn("assistant", json.dumps(result), "aegis")
        except Exception as e:
            self.hud.set_persona_status("aegis", "error")
            self._print("aegis", f"Error: {e}")
        finally:
            self.hud.set_persona_status("aegis", "idle")
            self._active_persona = ""

    async def _handle_fuzz(self, arg: str) -> None:
        self._active_persona = "aegis"
        self.hud.set_persona_status("aegis", "working")
        self._save_turn("user", arg[:200], "aegis")
        try:
            result = self.aegis.fuzz_inputs(arg)
            self.hud.set_persona_status("aegis", "done")
            self._print("aegis", json.dumps(result, indent=2))
            self._save_turn("assistant", json.dumps(result), "aegis")
        except Exception as e:
            self.hud.set_persona_status("aegis", "error")
            self._print("aegis", f"Error: {e}")
        finally:
            self.hud.set_persona_status("aegis", "idle")
            self._active_persona = ""

    async def _handle_surface(self, arg: str) -> None:
        self._active_persona = "aegis"
        self.hud.set_persona_status("aegis", "working")
        self._save_turn("user", arg[:200], "aegis")
        try:
            result = self.aegis.attack_surface_map(arg)
            self.hud.set_persona_status("aegis", "done")
            self._print("aegis", json.dumps(result, indent=2))
            self._save_turn("assistant", json.dumps(result), "aegis")
        except Exception as e:
            self.hud.set_persona_status("aegis", "error")
            self._print("aegis", f"Error: {e}")
        finally:
            self.hud.set_persona_status("aegis", "idle")
            self._active_persona = ""

    # ── Apis extended skills ──

    async def _handle_contract(self, arg: str) -> None:
        self._active_persona = "apis"
        self.hud.set_persona_status("apis", "working")
        self._save_turn("user", arg[:200], "apis")
        try:
            result = self.apis.validate_contract(arg)
            self.hud.set_persona_status("apis", "done")
            self._print("apis", json.dumps(result, indent=2))
            self._save_turn("assistant", json.dumps(result), "apis")
        except Exception as e:
            self.hud.set_persona_status("apis", "error")
            self._print("apis", f"Error: {e}")
        finally:
            self.hud.set_persona_status("apis", "idle")
            self._active_persona = ""

    async def _handle_loadtest(self, arg: str) -> None:
        self._active_persona = "apis"
        self.hud.set_persona_status("apis", "working")
        self._save_turn("user", arg, "apis")
        try:
            result = self.apis.load_test(arg)
            self.hud.set_persona_status("apis", "done")
            self._print("apis", result)
            self._save_turn("assistant", result, "apis")
        except Exception as e:
            self.hud.set_persona_status("apis", "error")
            self._print("apis", f"Error: {e}")
        finally:
            self.hud.set_persona_status("apis", "idle")
            self._active_persona = ""

    async def _handle_mockserver(self, arg: str) -> None:
        self._active_persona = "apis"
        self.hud.set_persona_status("apis", "working")
        self._save_turn("user", arg[:200], "apis")
        try:
            result = self.apis.mock_server(arg)
            self.hud.set_persona_status("apis", "done")
            self._print("apis", result)
            self._save_turn("assistant", result, "apis")
        except Exception as e:
            self.hud.set_persona_status("apis", "error")
            self._print("apis", f"Error: {e}")
        finally:
            self.hud.set_persona_status("apis", "idle")
            self._active_persona = ""

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
                "/provider": lambda: self._handle_provider(arg),
                "/status": lambda: self._handle_status(),
                "/hud": lambda: self._handle_hud(),
                # v0.3.0 extended skills
                "/refactor": lambda: self._handle_refactor(arg),
                "/tests": lambda: self._handle_tests(arg),
                "/convert": lambda: self._handle_convert(arg),
                "/document": lambda: self._handle_document(arg),
                "/deps": lambda: self._handle_deps(arg),
                "/diagram": lambda: self._handle_diagram(arg),
                "/estimate": lambda: self._handle_estimate(arg),
                "/scandeps": lambda: self._handle_scandeps(arg),
                "/owasp": lambda: self._handle_owasp(arg),
                "/compliance": lambda: self._handle_compliance(arg),
                "/profile": lambda: self._handle_profile(arg),
                "/trace": lambda: self._handle_trace(arg),
                "/stacktrace": lambda: self._handle_stacktrace(arg),
                "/mockup": lambda: self._handle_mockup(arg),
                "/naming": lambda: self._handle_naming(arg),
                "/brainstorm": lambda: self._handle_brainstorm(arg),
                "/changelog": lambda: self._handle_changelog(arg),
                "/diff": lambda: self._handle_diff(arg),
                "/meeting": lambda: self._handle_meeting(arg),
                "/threat": lambda: self._handle_threat(arg),
                "/fuzz": lambda: self._handle_fuzz(arg),
                "/surface": lambda: self._handle_surface(arg),
                "/contract": lambda: self._handle_contract(arg),
                "/loadtest": lambda: self._handle_loadtest(arg),
                "/mockserver": lambda: self._handle_mockserver(arg),
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
                                       "/apis", "/search", "/provider",
                                       "/refactor", "/tests", "/convert", "/document",
                                       "/deps", "/diagram", "/estimate",
                                       "/scandeps", "/owasp", "/compliance",
                                       "/profile", "/trace", "/stacktrace",
                                       "/mockup", "/naming", "/brainstorm",
                                       "/changelog", "/diff", "/meeting",
                                       "/threat", "/fuzz", "/surface",
                                       "/contract", "/loadtest", "/mockserver"):
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
        # Show initial HUD
        self._show_hud()

        while True:
            try:
                prompt_str = f"\n{C.YELLOW}\U0001f41d{C.RESET} {C.BOLD}>{C.RESET} "
                line = await asyncio.to_thread(input, prompt_str)
            except (EOFError, KeyboardInterrupt):
                self._print("hive", "Goodbye!")
                break

            should_continue = await self.dispatch(line)
            if not should_continue:
                break

            # Refresh HUD after each command
            self._show_hud()

        self.db.close()


def main() -> None:
    cli = HiveCLI()
    try:
        asyncio.run(cli.run())
    except KeyboardInterrupt:
        print(f"\n{C.RESET}Interrupted.")
        cli.db.close()


if __name__ == "__main__":
    main()
