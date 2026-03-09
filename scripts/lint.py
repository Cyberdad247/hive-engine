"""HIVE-specific linter -- checks for common issues in the codebase."""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path
from typing import NamedTuple

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

# Severity levels
ERROR = "ERROR"
WARNING = "WARNING"
INFO = "INFO"


class LintIssue(NamedTuple):
    file: str
    line: int
    severity: str
    rule: str
    message: str


# Secret patterns to flag
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("hardcoded_sk", re.compile(r'sk-[a-zA-Z0-9\-_]{20,}')),
    ("hardcoded_ghp", re.compile(r'ghp_[a-zA-Z0-9]{36,}')),
    ("hardcoded_aws", re.compile(r'AKIA[0-9A-Z]{16}')),
    ("hardcoded_password", re.compile(r'''password\s*=\s*["'][^"']{8,}["']''', re.IGNORECASE)),
    ("private_key", re.compile(r'-----BEGIN (?:RSA |EC )?PRIVATE KEY-----')),
]


def lint_file(filepath: Path) -> list[LintIssue]:
    """Lint a single Python file."""
    issues: list[LintIssue] = []
    rel = str(filepath.relative_to(PROJECT_ROOT))

    try:
        source = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return issues

    lines = source.splitlines()

    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()

        # Check for hardcoded secrets
        for rule_name, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                # Skip if it's in a comment about patterns or a regex definition
                if "re.compile" in line or "PATTERN" in line.upper() or "_PATTERNS" in line:
                    continue
                issues.append(LintIssue(
                    rel, lineno, ERROR, rule_name,
                    "Possible hardcoded secret detected",
                ))

        # Check for import *
        if re.match(r"^\s*from\s+\S+\s+import\s+\*", stripped):
            issues.append(LintIssue(
                rel, lineno, ERROR, "no_star_import",
                "Star import detected -- use explicit imports",
            ))

        # Check for bare except
        if re.match(r"^\s*except\s*:", stripped):
            issues.append(LintIssue(
                rel, lineno, WARNING, "bare_except",
                "Bare except: clause -- catch specific exceptions",
            ))

        # Check for TODO without ticket
        todo_match = re.search(r"#\s*TODO\b(.*)$", line, re.IGNORECASE)
        if todo_match:
            rest = todo_match.group(1).strip()
            # Check for ticket reference like HIVE-123, #123, etc.
            if not re.search(r"(HIVE-\d+|#\d+|\[.+\])", rest):
                issues.append(LintIssue(
                    rel, lineno, INFO, "todo_no_ticket",
                    "TODO without ticket reference",
                ))

        # Check for print() in core/ (should use logging)
        if rel.startswith("core" + str(Path("/").as_posix())[0:0]) or rel.startswith("core/") or rel.startswith("core\\"):
            if re.match(r"^\s*print\s*\(", stripped):
                issues.append(LintIssue(
                    rel, lineno, WARNING, "no_print_in_core",
                    "Use logging instead of print() in core/",
                ))

    # AST-level checks
    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        issues.append(LintIssue(rel, 0, ERROR, "syntax_error", "File has syntax errors"))
        return issues

    # Check persona class naming consistency
    if rel.startswith("personas/") or rel.startswith("personas\\"):
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Persona classes should be CamelCase
                if not node.name[0].isupper():
                    issues.append(LintIssue(
                        rel, node.lineno, WARNING, "persona_naming",
                        f"Class '{node.name}' should use CamelCase",
                    ))

    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description="HIVE Engine linter")
    parser.add_argument("--no-info", action="store_true",
                        help="Suppress info-level messages")
    parser.add_argument("paths", nargs="*", default=None,
                        help="Specific files/dirs to lint (default: entire project)")
    args = parser.parse_args()

    # Collect Python files
    if args.paths:
        files: list[Path] = []
        for p in args.paths:
            path = Path(p)
            if path.is_file() and path.suffix == ".py":
                files.append(path.resolve())
            elif path.is_dir():
                files.extend(path.resolve().rglob("*.py"))
    else:
        files = [
            f for f in PROJECT_ROOT.rglob("*.py")
            if ".hive" not in f.parts
            and "edge_build" not in f.parts
            and "__pycache__" not in f.parts
        ]

    all_issues: list[LintIssue] = []
    for filepath in sorted(files):
        issues = lint_file(filepath)
        all_issues.extend(issues)

    # Filter
    if args.no_info:
        all_issues = [i for i in all_issues if i.severity != INFO]

    # Report
    error_count = 0
    warning_count = 0
    info_count = 0

    for issue in all_issues:
        prefix = {"ERROR": "E", "WARNING": "W", "INFO": "I"}[issue.severity]
        print(f"{prefix} {issue.file}:{issue.line} [{issue.rule}] {issue.message}")
        if issue.severity == ERROR:
            error_count += 1
        elif issue.severity == WARNING:
            warning_count += 1
        else:
            info_count += 1

    print(f"\n{len(all_issues)} issues: {error_count} errors, "
          f"{warning_count} warnings, {info_count} info")

    if error_count > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
