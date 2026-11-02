#!/usr/bin/env python3
"""
Guardrail: all backend calls go through frontend/src/lib/api.ts.

Counts, per file under frontend/src, three kinds of drift:
  urls     string literals containing '/api/method/' or '/api/resource'
           (exempt: lib/api.ts, lib/api.test.ts, services/**)
  fetch    raw `fetch(` calls (exempt: lib/api.ts, services/**)
  helpers  functions named invoke / unwrap* / callApi defined outside lib/api.ts

The counts are compared with scripts/baselines/api_calls.json. The check fails if
any file's count increases or a file with a nonzero count is not in the baseline.
Baselines may only go down.

Usage:
    python3 scripts/check_api_calls.py            # check (exit 1 on regression)
    python3 scripts/check_api_calls.py --list     # print every offender
    python3 scripts/check_api_calls.py --update   # rewrite baseline (decreases only)
    python3 scripts/check_api_calls.py --update --force   # allow increases
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_REL = "frontend/src"
BASELINE = ROOT / "scripts" / "baselines" / "api_calls.json"

CATEGORIES = ("urls", "fetch", "helpers")
EXTS = {".ts", ".tsx", ".js", ".jsx", ".mjs"}

URL_EXEMPT_FILES = {"lib/api.ts", "lib/api.test.ts"}
FETCH_EXEMPT_FILES = {"lib/api.ts"}
SERVICES_PREFIX = "services/"
HELPER_HOME = "lib/api.ts"

URL_RE = re.compile(r"""(["'`])(?:(?!\1)[^\n\\]|\\.)*?/api/(?:method/|resource)(?:(?!\1)[^\n\\]|\\.)*?\1""")
FETCH_RE = re.compile(r"(?<![\w$.])fetch\s*\(|\b(?:window|globalThis)\.fetch\s*\(")
HELPER_RE = re.compile(
    r"\b(?:function\s*\*?\s+|(?:const|let|var)\s+)(invoke|unwrap\w*|callApi)\b(?!\s*:\s*[^=]*;)"
)


def _is_comment(line: str) -> bool:
    s = line.lstrip()
    return s.startswith(("//", "*", "/*"))


def count_file(rel: str, text: str) -> dict[str, int]:
    """Counts for one file; `rel` is the path relative to frontend/src (posix)."""
    in_services = rel.startswith(SERVICES_PREFIX)
    counts = {c: 0 for c in CATEGORIES}
    for line in text.splitlines():
        if _is_comment(line):
            continue
        if not in_services and rel not in URL_EXEMPT_FILES:
            counts["urls"] += len(URL_RE.findall(line))
        if not in_services and rel not in FETCH_EXEMPT_FILES:
            counts["fetch"] += len(FETCH_RE.findall(line))
        if rel != HELPER_HOME:
            counts["helpers"] += len(HELPER_RE.findall(line))
    return counts


def scan(root: Path | None = None) -> dict[str, dict[str, int]]:
    src = (root or ROOT) / SRC_REL
    result: dict[str, dict[str, int]] = {}
    for path in sorted(src.rglob("*")):
        if path.suffix not in EXTS or not path.is_file() or "node_modules" in path.parts:
            continue
        rel = path.relative_to(src).as_posix()
        counts = count_file(rel, path.read_text(encoding="utf-8", errors="replace"))
        if any(counts.values()):
            result[rel] = {c: n for c, n in counts.items() if n}
    return result


def load_baseline(path: Path | None = None) -> dict[str, dict[str, int]]:
    path = path or BASELINE
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def compare(current: dict, baseline: dict) -> list[str]:
    """Regressions: any category count above its baseline (missing baseline = 0)."""
    problems = []
    for rel, counts in sorted(current.items()):
        base = baseline.get(rel, {})
        for cat, n in sorted(counts.items()):
            allowed = base.get(cat, 0)
            if n > allowed:
                kind = "new file" if rel not in baseline else "increased"
                problems.append(f"{rel}: {cat} {allowed} -> {n} ({kind})")
    return problems


def totals(data: dict) -> dict[str, int]:
    t = {c: 0 for c in CATEGORIES}
    for counts in data.values():
        for c, n in counts.items():
            t[c] += n
    return t


def write_baseline(data: dict, path: Path | None = None) -> None:
    path = path or BASELINE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(sorted(data.items())), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--update", action="store_true", help="rewrite the baseline (decreases only)")
    ap.add_argument("--force", action="store_true", help="with --update, allow increases")
    ap.add_argument("--list", action="store_true", help="print all offenders")
    args = ap.parse_args(argv)

    current = scan()
    baseline = load_baseline()

    if args.list:
        for rel, counts in sorted(current.items()):
            print(f"{rel}: " + ", ".join(f"{c}={n}" for c, n in counts.items()))
        print("totals: " + ", ".join(f"{c}={n}" for c, n in totals(current).items()))
        return 0

    problems = compare(current, baseline)

    if args.update:
        if problems and not args.force:
            print("Refusing to raise the baseline (use --force to override):")
            for p in problems:
                print(f"  {p}")
            return 1
        write_baseline(current)
        print("Baseline written. totals: " + ", ".join(f"{c}={n}" for c, n in totals(current).items()))
        return 0

    if problems:
        print("API call drift increased. Use apiCall() from frontend/src/lib/api.ts instead:")
        for p in problems:
            print(f"  {p}")
        print("(run with --list to see every offender; baselines may only decrease)")
        return 1

    stale = [r for r in baseline if r not in current or any(current[r].get(c, 0) < baseline[r].get(c, 0) for c in baseline[r])]
    if stale:
        print(f"note: {len(stale)} file(s) improved; run with --update to lower the baseline.")
    print("API call check OK. totals: " + ", ".join(f"{c}={n}" for c, n in totals(current).items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
