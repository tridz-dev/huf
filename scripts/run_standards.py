#!/usr/bin/env python3
"""
Run every standards guard listed in scripts/standards.json and print one table.

Each manifest entry is {name, script, args, paths}. Adding a guard means adding
an entry to the manifest only; CI and pre-commit already call this runner. An
entry whose script does not exist yet is skipped with a warning, so branches
that add guards can merge in any order.

Usage:
    python3 scripts/run_standards.py                  # run all guards
    python3 scripts/run_standards.py --only file-size # run one guard
    python3 scripts/run_standards.py --update         # pass --update to each guard
    python3 scripts/run_standards.py --files a b      # only guards whose `paths` match
"""

import argparse
import fnmatch
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path(__file__).resolve().parent / "standards.json"


def matches(entry, files):
    pats = entry.get("paths") or ["**"]
    return any(fnmatch.fnmatch(f, p) or fnmatch.fnmatch(f, p.replace("**/", "")) for f in files for p in pats)


def run_entry(entry, root, update, verbose_ok=False):
    script = root / entry["script"]
    if not script.exists():
        return "SKIP", 0.0, f"warning: {entry['script']} does not exist yet, skipping"
    cmd = [sys.executable, str(script), *entry.get("args", [])]
    if update:
        cmd.append("--update")
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
    out = (proc.stdout + proc.stderr).strip()
    return ("PASS" if proc.returncode == 0 else "FAIL"), time.time() - t0, out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--only", action="append", default=[], help="run only this guard name (repeatable)")
    ap.add_argument("--update", action="store_true", help="pass --update to each guard")
    ap.add_argument("--files", nargs="*", help="changed files; run only guards whose paths match")
    ap.add_argument("-v", "--verbose", action="store_true", help="show output of passing guards")
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    ap.add_argument("--root", type=Path, default=ROOT)
    args = ap.parse_args(argv)

    entries = json.loads(args.manifest.read_text())
    if args.only:
        unknown = set(args.only) - {e["name"] for e in entries}
        if unknown:
            print("Unknown guard(s): " + ", ".join(sorted(unknown)))
            return 2
        entries = [e for e in entries if e["name"] in args.only]
    if args.files is not None:
        entries = [e for e in entries if matches(e, args.files)]

    rows, details = [], []
    for e in entries:
        status, secs, out = run_entry(e, args.root, args.update)
        rows.append((e["name"], status, secs))
        if status != "PASS" and out:
            details.append((e["name"], out))
        elif status == "PASS" and out and args.verbose:
            details.append((e["name"], out))

    for name, out in details:
        print(f"--- {name}")
        print(out)
    width = max([len(r[0]) for r in rows] + [5])
    print()
    print(f"{'GUARD'.ljust(width)}  {'STATUS':6}  TIME")
    for name, status, secs in rows:
        print(f"{name.ljust(width)}  {status:6}  {secs:.2f}s")
    failed = [r[0] for r in rows if r[1] == "FAIL"]
    if failed:
        print("\nFAILED: " + ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
