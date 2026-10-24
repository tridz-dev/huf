#!/usr/bin/env python3
"""UI drift guard: per-file counts of form/UI anti-patterns in frontend/src.

Rules (counted per file):
  raw_element   raw <label|input|select|textarea> outside components/ui/**
  fixed_height  h-6..h-11 on <Input|Button|SelectTrigger|Textarea|InputGroup> tags
  text_px       text-[Npx] arbitrary font sizes
  hex_colour    #rgb/#rrggbb(aa) literals inside strings of .tsx files
  inline_style  style={{ ... }}

The committed baseline (scripts/baselines/ui_drift.json) records today's counts.
The check fails when any file's count rises or a new file has non-zero counts.
Counts may only go down: `--update` rewrites the baseline and refuses increases
unless `--force` is given.

Usage:
  python3 scripts/check_ui_drift.py            # check (exit 1 on drift)
  python3 scripts/check_ui_drift.py --list     # print current per-file counts
  python3 scripts/check_ui_drift.py --update   # ratchet baseline down
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC_DEFAULT = REPO / "frontend" / "src"
BASELINE_DEFAULT = REPO / "scripts" / "baselines" / "ui_drift.json"

RULES = ("raw_element", "fixed_height", "text_px", "hex_colour", "inline_style")
RULE_HELP = {
    "raw_element": "raw <label|input|select|textarea>: use ui/field, ui/input, ui/select, ui/textarea, ui/label",
    "fixed_height": "h-6..h-11 on a control: use the control size prop / h-control-* tokens",
    "text_px": "text-[Npx]: use the type tokens (text-micro, text-ui-text, ...)",
    "hex_colour": "hex colour literal: use a design token / CSS variable",
    "inline_style": "style={{ }}: use classes or tokens (dynamic geometry may need a baseline entry)",
}

EXTS = {".ts", ".tsx", ".jsx"}
CONTROL_TAG = re.compile(r"<(?:Input|Button|SelectTrigger|Textarea|InputGroup)\b")
FIXED_H = re.compile(r"(?<![\w-])h-(?:6|7|8|9|10|11)(?![\w.\-/])")
RAW_EL = re.compile(r"<(?:label|input|select|textarea)(?=[\s/>])")
TEXT_PX = re.compile(r"text-\[\d+px\]")
HEX = re.compile(r"(?<![\w&])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})(?![\w-])")
STYLE = re.compile(r"\bstyle=\{\{")
STRING = re.compile(r"""'(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*"|`(?:[^`\\]|\\.)*`""", re.S)
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
LINE_COMMENT = re.compile(r"(?m)(?:^|(?<=\s))//.*$")


def strip_comments(text: str) -> str:
    """Blank out comments, preserving offsets' line structure."""
    text = BLOCK_COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    return LINE_COMMENT.sub("", text)


def tag_end(text: str, start: int) -> int:
    """Index just past the '>' closing the JSX opening tag that starts at `start`."""
    depth = 0
    quote = ""
    i = start
    n = len(text)
    while i < n:
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = ""
        elif ch in "\"'`":
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == ">" and depth <= 0:
            return i + 1
        i += 1
    return n


def count_fixed_height(text: str) -> int:
    total = 0
    for m in CONTROL_TAG.finditer(text):
        total += len(FIXED_H.findall(text[m.start():tag_end(text, m.end())]))
    return total


def count_hex(text: str) -> int:
    return sum(len(HEX.findall(s.group(0))) for s in STRING.finditer(text))


def scan_text(text: str, rel: str) -> dict[str, int]:
    text = strip_comments(text)
    in_ui = rel.startswith("components/ui/")
    out = {
        "raw_element": 0 if in_ui else len(RAW_EL.findall(text)),
        "fixed_height": count_fixed_height(text),
        "text_px": len(TEXT_PX.findall(text)),
        "hex_colour": count_hex(text) if rel.endswith((".tsx", ".jsx")) else 0,
        "inline_style": len(STYLE.findall(text)),
    }
    return {k: v for k, v in out.items() if v}


def is_scanned(rel: str) -> bool:
    p = Path(rel)
    if p.suffix not in EXTS or p.name.endswith(".d.ts"):
        return False
    if ".test." in p.name or ".spec." in p.name or "__tests__" in p.parts or "__mocks__" in p.parts:
        return False
    return True


def scan(src: Path) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for path in sorted(src.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(src).as_posix()
        if not is_scanned(rel):
            continue
        counts = scan_text(path.read_text(encoding="utf-8", errors="replace"), rel)
        if counts:
            result[rel] = counts
    return result


def totals(files: dict[str, dict[str, int]]) -> dict[str, int]:
    t = {r: 0 for r in RULES}
    for c in files.values():
        for r, n in c.items():
            t[r] += n
    return t


def diff(current, baseline):
    """Return (increases, decreases); each a list of (file, rule, old, new)."""
    inc, dec = [], []
    for f in sorted(set(current) | set(baseline)):
        for r in RULES:
            old = baseline.get(f, {}).get(r, 0)
            new = current.get(f, {}).get(r, 0)
            if new > old:
                inc.append((f, r, old, new))
            elif new < old:
                dec.append((f, r, old, new))
    return inc, dec


def report(rows, title, out=sys.stdout):
    print(title, file=out)
    cur = None
    for f, r, old, new in rows:
        if f != cur:
            print(f"  {f}", file=out)
            cur = f
        print(f"    {r}: {old} -> {new}", file=out)


def load_baseline(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text())["files"]


def write_baseline(path: Path, files):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"version": 1, "totals": totals(files), "files": files}
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--update", action="store_true", help="rewrite baseline (decreases only)")
    ap.add_argument("--force", action="store_true", help="with --update, allow increases")
    ap.add_argument("--list", action="store_true", help="print current per-file counts")
    ap.add_argument("--src", type=Path, default=SRC_DEFAULT)
    ap.add_argument("--baseline", type=Path, default=BASELINE_DEFAULT)
    args = ap.parse_args(argv)

    current = scan(args.src)
    baseline_exists = args.baseline.exists()
    baseline = load_baseline(args.baseline)

    if args.list:
        for f, c in sorted(current.items()):
            print(f"{f}\t" + " ".join(f"{r}={c[r]}" for r in RULES if r in c))
        t = totals(current)
        print("TOTAL\t" + " ".join(f"{r}={t[r]}" for r in RULES))
        return 0

    if not baseline_exists and not args.update:
        print(f"No baseline at {args.baseline}; create it with --update.", file=sys.stderr)
        return 1
    inc, dec = diff(current, baseline)

    if args.update:
        if inc and baseline_exists and not args.force:
            report(inc, "Refusing to update: counts would increase (baselines only go down; fix the code or pass --force):", sys.stderr)
            return 1
        write_baseline(args.baseline, current)
        print(f"Baseline written: {args.baseline} totals={totals(current)}")
        return 0

    if inc:
        report(inc, "UI drift: counts rose above the baseline (file / rule: baseline -> now):", sys.stderr)
        print("\nRules:", file=sys.stderr)
        for r in sorted({r for _, r, _, _ in inc}):
            print(f"  {r}: {RULE_HELP[r]}", file=sys.stderr)
        print("\nFix the code. Do not raise the baseline.", file=sys.stderr)
        return 1
    t = totals(current)
    print("UI drift OK: " + " ".join(f"{r}={t[r]}" for r in RULES))
    if dec:
        print(f"{len(dec)} file/rule counts dropped below the baseline; run `python3 scripts/check_ui_drift.py --update` to ratchet it down.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
