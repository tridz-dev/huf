#!/usr/bin/env python3
"""
Pre-commit / CI guardrail for explicit frappe.db.commit() calls.

This script mirrors the huf-no-explicit-frappe-commit semgrep rule so the
check can run without requiring semgrep to be installed. It scans the given
Python files and fails if any line calls frappe.db.commit() unless:

  - the line contains a '# nosemgrep' justification comment, or
  - the file is in the known-allowlist of justified locations.

Usage:
    python scripts/check_explicit_commits.py file1.py file2.py ...
"""

import argparse
import fnmatch
import sys
from pathlib import Path


ALLOWLIST_PATTERNS = [
    "huf/install.py",
    "huf/patches/**/*.py",
    "huf/www/huf.py",
    "huf/ai/knowledge/indexer.py",
    "huf/ai/orchestration/orchestrator.py",
    "huf/ai/orchestration/scheduler.py",
    "huf/ai/agent_scheduler.py",
    "huf/ai/app_seeding/tests/test_seed_fk.py",
    "huf/ai/transaction.py",
]


def _matches_allowlist(rel_path: str) -> bool:
    for pattern in ALLOWLIST_PATTERNS:
        if pattern.endswith("/**/*.py"):
            prefix = pattern.removesuffix("/**/*.py")
            if rel_path.startswith(prefix + "/") and rel_path.endswith(".py"):
                return True
        if fnmatch.fnmatch(rel_path, pattern):
            return True
    return False


def check_file(path: Path) -> list[tuple[int, str]]:
    violations = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return violations

    for lineno, line in enumerate(text.splitlines(), start=1):
        if "frappe.db.commit()" in line:
            if "# nosemgrep" in line:
                continue
            violations.append((lineno, line.rstrip()))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Guard against explicit frappe.db.commit() calls."
    )
    parser.add_argument("files", nargs="+", help="Python files to check")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parent.parent
    exit_code = 0

    for file_path in args.files:
        path = Path(file_path)
        try:
            rel_path = path.resolve().relative_to(root).as_posix()
        except ValueError:
            # File is outside the project root; skip it.
            continue

        if not rel_path.startswith("huf/") or not rel_path.endswith(".py"):
            continue

        if _matches_allowlist(rel_path):
            continue

        violations = check_file(path)
        for lineno, line in violations:
            print(
                f"{rel_path}:{lineno}: explicit frappe.db.commit() found. "
                "Use a transaction helper or add '# nosemgrep' with justification."
            )
            print(f"    {line.strip()}")
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
