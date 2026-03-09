"""Semver version management for HIVE Engine."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
VERSION_FILE = PROJECT_ROOT / "VERSION"
CHANGELOG_FILE = PROJECT_ROOT / "CHANGELOG.md"


def read_version() -> str:
    """Read current version from VERSION file."""
    if not VERSION_FILE.exists():
        VERSION_FILE.write_text("0.1.0\n")
    return VERSION_FILE.read_text().strip()


def write_version(version: str) -> None:
    """Write version to VERSION file."""
    VERSION_FILE.write_text(version + "\n")


def parse_semver(version: str) -> tuple[int, int, int]:
    """Parse a semver string into (major, minor, patch)."""
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", version)
    if not match:
        raise ValueError(f"Invalid semver: {version}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def bump_version(current: str, part: str) -> str:
    """Bump a version by the specified part."""
    major, minor, patch = parse_semver(current)
    if part == "major":
        return f"{major + 1}.0.0"
    elif part == "minor":
        return f"{major}.{minor + 1}.0"
    elif part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    else:
        raise ValueError(f"Unknown part: {part}. Use major/minor/patch.")


def get_git_log(since_tag: str | None = None) -> list[str]:
    """Get git log entries since the last tag (or all if no tag)."""
    try:
        cmd = ["git", "log", "--oneline", "--no-decorate"]
        if since_tag:
            cmd.append(f"{since_tag}..HEAD")
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT)
        )
        if result.returncode == 0:
            return [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
    except FileNotFoundError:
        pass
    return []


def get_latest_tag() -> str | None:
    """Get the most recent git tag."""
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    return None


def create_git_tag(version: str) -> bool:
    """Create a git tag for the version."""
    tag = f"v{version}"
    try:
        result = subprocess.run(
            ["git", "tag", "-a", tag, "-m", f"Release {tag}"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        )
        if result.returncode == 0:
            print(f"Created git tag: {tag}")
            return True
        else:
            print(f"Failed to create tag: {result.stderr}", file=sys.stderr)
            return False
    except FileNotFoundError:
        print("git not found", file=sys.stderr)
        return False


def update_changelog(version: str, entries: list[str]) -> None:
    """Append a changelog entry."""
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new_entry = f"\n## [{version}] - {date_str}\n\n"
    if entries:
        for entry in entries:
            # Strip the commit hash prefix
            parts = entry.split(" ", 1)
            msg = parts[1] if len(parts) > 1 else parts[0]
            new_entry += f"- {msg}\n"
    else:
        new_entry += "- Release\n"

    if CHANGELOG_FILE.exists():
        existing = CHANGELOG_FILE.read_text()
        # Insert after the header
        header_end = existing.find("\n## ")
        if header_end > 0:
            updated = existing[:header_end] + new_entry + existing[header_end:]
        else:
            updated = existing + new_entry
    else:
        updated = f"# Changelog\n{new_entry}"

    CHANGELOG_FILE.write_text(updated)
    print(f"Updated {CHANGELOG_FILE}")


def get_version_history() -> list[str]:
    """Get version history from git tags."""
    try:
        result = subprocess.run(
            ["git", "tag", "-l", "v*", "--sort=-version:refname"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        )
        if result.returncode == 0:
            return [t.strip() for t in result.stdout.strip().splitlines() if t.strip()]
    except FileNotFoundError:
        pass
    return []


def cmd_show() -> None:
    """Show current version."""
    print(read_version())


def cmd_bump(part: str, tag: bool = False) -> None:
    """Bump version."""
    current = read_version()
    new_version = bump_version(current, part)
    write_version(new_version)
    print(f"{current} -> {new_version}")

    # Update changelog
    latest_tag = get_latest_tag()
    entries = get_git_log(latest_tag)
    update_changelog(new_version, entries)

    if tag:
        create_git_tag(new_version)


def cmd_history() -> None:
    """Show version history."""
    tags = get_version_history()
    if tags:
        print("Version history:")
        for t in tags:
            print(f"  {t}")
    else:
        print(f"No tags found. Current: {read_version()}")


def cmd_rollback() -> None:
    """Rollback to previous version (from git tags)."""
    tags = get_version_history()
    if len(tags) < 2:
        print("No previous version to rollback to.", file=sys.stderr)
        sys.exit(1)
    previous = tags[1].lstrip("v")
    current = read_version()
    write_version(previous)
    print(f"Rolled back: {current} -> {previous}")


def main() -> None:
    parser = argparse.ArgumentParser(description="HIVE Engine version management")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("show", help="Show current version")

    bump_parser = sub.add_parser("bump", help="Bump version")
    bump_parser.add_argument("part", choices=["patch", "minor", "major"])
    bump_parser.add_argument("--tag", action="store_true", help="Create git tag")

    sub.add_parser("history", help="Show version history from git tags")
    sub.add_parser("rollback", help="Rollback to previous version")

    args = parser.parse_args()

    if args.command == "show" or args.command is None:
        cmd_show()
    elif args.command == "bump":
        cmd_bump(args.part, tag=args.tag)
    elif args.command == "history":
        cmd_history()
    elif args.command == "rollback":
        cmd_rollback()


if __name__ == "__main__":
    main()
