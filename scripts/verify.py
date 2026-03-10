"""HIVE Engine verification script -- checks project integrity."""

from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

# Resolve project root
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent


class VerifyResult:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        if condition:
            self.passed.append(name)
            print(f"  PASS  {name}")
        else:
            msg = f"{name}: {detail}" if detail else name
            self.failed.append(msg)
            print(f"  FAIL  {msg}")


def main() -> None:
    print("HIVE Engine Verification\n" + "=" * 40)
    result = VerifyResult()

    # 1. Core files exist
    core_files = [
        "core/__init__.py",
        "core/router.py",
        "core/memory.py",
        "core/memory_db.py",
        "core/hnsw.py",
        "core/pipeline.py",
        "core/feedback.py",
    ]
    for f in core_files:
        path = PROJECT_ROOT / f
        result.check(f"core file: {f}", path.exists(), f"Missing: {path}")

    # 2. Persona files exist
    persona_files = [
        "personas/__init__.py",
        "personas/base.py",
        "personas/forge.py",
        "personas/oracle.py",
        "personas/sentinel.py",
        "personas/debug.py",
        "personas/muse.py",
        "personas/coda.py",
        "personas/aegis.py",
        "personas/apis.py",
    ]
    for f in persona_files:
        path = PROJECT_ROOT / f
        result.check(f"persona file: {f}", path.exists(), f"Missing: {path}")

    # 3. VERSION file valid semver
    version_path = PROJECT_ROOT / "VERSION"
    if version_path.exists():
        version_text = version_path.read_text().strip()
        semver_ok = bool(re.match(r"^\d+\.\d+\.\d+$", version_text))
        result.check("VERSION is valid semver", semver_ok,
                      f"Got: {version_text!r}")
    else:
        result.check("VERSION file exists", False, "Missing VERSION file")

    # 4. .env.example exists
    result.check(".env.example exists",
                 (PROJECT_ROOT / ".env.example").exists())

    # 5. .gitignore has .env and .hive/
    gitignore_path = PROJECT_ROOT / ".gitignore"
    if gitignore_path.exists():
        gitignore = gitignore_path.read_text(encoding="utf-8")
        result.check(".gitignore has .env",
                      ".env" in gitignore, "Missing .env in .gitignore")
        result.check(".gitignore has .hive/",
                      ".hive/" in gitignore, "Missing .hive/ in .gitignore")
    else:
        result.check(".gitignore exists", False)

    # 6. All personas have iron_gate_check (or inherit it)
    for pf in persona_files[2:]:  # skip __init__.py and base.py
        path = PROJECT_ROOT / pf
        if path.exists():
            source = path.read_text(encoding="utf-8")
            try:
                tree = ast.parse(source)
                classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
                has_persona_base = False
                for cls in classes:
                    for base in cls.bases:
                        base_name = ""
                        if isinstance(base, ast.Name):
                            base_name = base.id
                        elif isinstance(base, ast.Attribute):
                            base_name = base.attr
                        if base_name == "Persona":
                            has_persona_base = True
                            break
                result.check(f"{pf} inherits Persona (has iron_gate_check)",
                             has_persona_base,
                             "Class does not inherit from Persona")
            except SyntaxError as e:
                result.check(f"{pf} syntax valid", False, str(e))

    # 7. MCP server has all 15 tools
    mcp_path = PROJECT_ROOT / "mcp_server.py"
    if mcp_path.exists():
        mcp_source = mcp_path.read_text(encoding="utf-8")
        expected_tools = [
            "hive_oracle", "hive_forge", "hive_sentinel", "hive_heal",
            "hive_muse", "hive_coda_compress", "hive_coda_verify",
            "hive_aegis", "hive_aegis_prompt", "hive_apis_test",
            "hive_apis_crawl", "hive_pipeline", "hive_memory_search",
            "hive_memory_stats", "hive_rate",
            # v0.3.0 new skills
            "hive_forge_refactor", "hive_forge_tests", "hive_forge_convert",
            "hive_forge_document",
            "hive_oracle_deps", "hive_oracle_diagram", "hive_oracle_estimate",
            "hive_sentinel_deps", "hive_sentinel_owasp", "hive_sentinel_compliance",
            "hive_debug_profile", "hive_debug_trace", "hive_debug_stacktrace",
            "hive_muse_mockup", "hive_muse_naming", "hive_muse_brainstorm",
            "hive_coda_changelog", "hive_coda_diff", "hive_coda_meeting",
            "hive_aegis_threat", "hive_aegis_fuzz", "hive_aegis_surface",
            "hive_apis_contract", "hive_apis_loadtest", "hive_apis_mock",
        ]
        for tool in expected_tools:
            result.check(f"MCP tool: {tool}",
                         f'"{tool}"' in mcp_source,
                         f"Tool {tool} not found in mcp_server.py")
    else:
        result.check("mcp_server.py exists", False)

    # 8. CLI has all commands
    cli_path = PROJECT_ROOT / "cli.py"
    if cli_path.exists():
        cli_source = cli_path.read_text(encoding="utf-8")
        expected_commands = [
            "/run", "/forge", "/oracle", "/sentinel", "/heal", "/muse",
            "/compress", "/aegis", "/apis", "/rate", "/learn", "/search",
            "/history", "/stats", "/resume", "/help", "/quit",
            # v0.3.0 new skills
            "/refactor", "/tests", "/convert", "/document",
            "/deps", "/diagram", "/estimate",
            "/scandeps", "/owasp", "/compliance",
            "/profile", "/trace", "/stacktrace",
            "/mockup", "/naming", "/brainstorm",
            "/changelog", "/diff", "/meeting",
            "/threat", "/fuzz", "/surface",
            "/contract", "/loadtest", "/mockserver",
        ]
        for cmd in expected_commands:
            result.check(f"CLI command: {cmd}",
                         f'"{cmd}"' in cli_source,
                         f"Command {cmd} not found in cli.py")
    else:
        result.check("cli.py exists", False)

    # 9. CI workflow exists
    ci_path = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
    result.check("CI workflow exists", ci_path.exists())

    # 10. Claude settings exist
    claude_path = PROJECT_ROOT / ".claude" / "settings.json"
    result.check(".claude/settings.json exists", claude_path.exists())

    # Summary
    total = len(result.passed) + len(result.failed)
    print(f"\n{'=' * 40}")
    print(f"Results: {len(result.passed)}/{total} passed, "
          f"{len(result.failed)} failed")

    if result.failed:
        print("\nFailed checks:")
        for f in result.failed:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("\nAll checks passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
