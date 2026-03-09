"""AST-based minifier that bundles HIVE Engine into a single .py file."""

from __future__ import annotations

import argparse
import ast
import gzip
import importlib.util
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
OUTPUT_DIR = PROJECT_ROOT / "edge_build"

# Build profiles: profile name -> list of modules to include
PROFILES: dict[str, list[str]] = {
    "standard": [
        "core/__init__.py",
        "core/router.py",
        "core/memory.py",
        "core/memory_db.py",
        "core/hnsw.py",
        "core/pipeline.py",
        "core/feedback.py",
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
    ],
    "minimal": [
        "core/__init__.py",
        "core/router.py",
        "core/memory.py",
        "personas/__init__.py",
        "personas/base.py",
        "personas/forge.py",
        "personas/sentinel.py",
        "personas/debug.py",
    ],
}


def minify_source(source: str) -> str:
    """Remove docstrings and comments, collapse blank lines."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source  # Return as-is if we can't parse

    # Remove docstrings
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, (ast.Constant, ast.Str))):
                # Replace docstring with pass if it's the only statement
                if len(node.body) == 1:
                    node.body[0] = ast.Pass()
                else:
                    node.body.pop(0)

    # Unparse back to source
    try:
        minified = ast.unparse(tree)
    except AttributeError:
        # Python < 3.9 fallback
        return source

    # Collapse multiple blank lines
    lines = minified.splitlines()
    result: list[str] = []
    prev_blank = False
    for line in lines:
        is_blank = not line.strip()
        if is_blank and prev_blank:
            continue
        result.append(line)
        prev_blank = is_blank

    return "\n".join(result)


def build_bundle(profile: str, minify: bool = True) -> str:
    """Build a single-file bundle from a profile."""
    modules = PROFILES.get(profile)
    if not modules:
        raise ValueError(f"Unknown profile: {profile}. Available: {list(PROFILES.keys())}")

    parts: list[str] = [
        '"""HIVE Engine - Edge Build ({profile})"""',
        f"# Profile: {profile}",
        f"# Modules: {len(modules)}",
        "",
        "from __future__ import annotations",
        "import asyncio, json, logging, math, os, random, re, sqlite3, subprocess",
        "import sys, time, uuid",
        "from abc import ABC, abstractmethod",
        "from collections import deque",
        "from dataclasses import dataclass, field",
        "from pathlib import Path",
        "from typing import Any",
        "",
    ]

    for module_path in modules:
        full_path = PROJECT_ROOT / module_path
        if not full_path.exists():
            parts.append(f"# MISSING: {module_path}")
            continue

        source = full_path.read_text(encoding="utf-8")
        if not source.strip():
            continue  # Skip empty __init__.py files

        # Remove future imports and duplicate stdlib imports (handled in header)
        cleaned_lines: list[str] = []
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("from __future__"):
                continue
            if stripped.startswith("import ") and any(
                mod in stripped for mod in [
                    "asyncio", "json", "logging", "math", "os", "random",
                    "re", "sqlite3", "subprocess", "sys", "time", "uuid",
                ]
            ):
                continue
            if stripped.startswith("from abc import"):
                continue
            if stripped.startswith("from collections import"):
                continue
            if stripped.startswith("from dataclasses import"):
                continue
            if stripped.startswith("from pathlib import"):
                continue
            if stripped.startswith("from typing import"):
                continue
            cleaned_lines.append(line)

        section_source = "\n".join(cleaned_lines)

        if minify:
            section_source = minify_source(section_source)

        parts.append(f"\n# {'=' * 60}")
        parts.append(f"# Module: {module_path}")
        parts.append(f"# {'=' * 60}")
        parts.append(section_source)

    return "\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="HIVE Engine edge builder")
    parser.add_argument("--profile", default="standard",
                        choices=list(PROFILES.keys()),
                        help="Build profile (default: standard)")
    parser.add_argument("--validate", action="store_true",
                        help="Import the bundle to check syntax")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show sizes without writing files")
    parser.add_argument("--no-minify", action="store_true",
                        help="Skip minification")
    args = parser.parse_args()

    print(f"Building edge bundle: profile={args.profile}")

    bundle = build_bundle(args.profile, minify=not args.no_minify)
    bundle_bytes = bundle.encode("utf-8")
    compressed = gzip.compress(bundle_bytes)

    py_size = len(bundle_bytes)
    gz_size = len(compressed)
    ratio = (1 - gz_size / py_size) * 100 if py_size > 0 else 0

    print(f"  .py size:  {py_size:,} bytes")
    print(f"  .gz size:  {gz_size:,} bytes ({ratio:.1f}% reduction)")
    print(f"  Modules:   {len(PROFILES[args.profile])}")

    if args.dry_run:
        print("Dry run -- no files written.")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    py_path = OUTPUT_DIR / f"hive_{args.profile}.py"
    gz_path = OUTPUT_DIR / f"hive_{args.profile}.py.gz"

    py_path.write_text(bundle, encoding="utf-8")
    gz_path.write_bytes(compressed)
    print(f"  Written: {py_path}")
    print(f"  Written: {gz_path}")

    if args.validate:
        print("Validating bundle syntax...")
        try:
            ast.parse(bundle)
            print("  AST parse: OK")
        except SyntaxError as e:
            print(f"  AST parse: FAIL - {e}", file=sys.stderr)
            sys.exit(1)

        # Try to compile (catches more issues than parse)
        try:
            compile(bundle, str(py_path), "exec")
            print("  Compile: OK")
        except Exception as e:
            print(f"  Compile: FAIL - {e}", file=sys.stderr)
            sys.exit(1)

        print("  Validation passed!")


if __name__ == "__main__":
    main()
