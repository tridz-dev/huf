#!/usr/bin/env python3
"""
Guard: core code may not gain new dependencies on the WhatsApp or Solutions features.

An "edge" is one core file referencing one feature module:
  * Python (huf/**/*.py): any import (module level or lazy, inside a function) of
    huf.ai.whatsapp*, huf.ai.solutions* or huf.ai.gateway_adapters.whatsapp*, plus
    dotted-path string literals naming those modules (hooks.py, frappe.get_attr, ...).
  * Frontend (frontend/src/**/*.ts(x)): an import / dynamic import / re-export whose
    specifier points into components/whatsapp, components/solutions, or the
    whatsappApi / solutionsApi services.

Feature-owned paths are not core and are skipped (see FEATURE_PATHS). Tests are skipped.

The baseline (scripts/baselines/core_boundary.json) lists the known edges. A new edge
fails; removed edges are reported so the baseline can be shrunk with --update.

Usage:
    python3 scripts/check_core_boundary.py            # check
    python3 scripts/check_core_boundary.py --list     # current edges grouped by file
    python3 scripts/check_core_boundary.py --update   # rewrite baseline (decreases only)
    python3 scripts/check_core_boundary.py --update --force   # allow increases
"""

import argparse
import ast
import json
import re
import sys
from pathlib import Path

PY_TARGET = re.compile(r"^huf\.ai\.(whatsapp|solutions|gateway_adapters\.whatsapp\w*)(\.|$)")
PY_STRING = re.compile(r"\bhuf\.ai\.(?:whatsapp|solutions|gateway_adapters\.whatsapp\w*)(?:\.\w+)*")
FE_IMPORT = re.compile(
    r"""(?:\bfrom\s*|\bimport\s*\(\s*|^\s*import\s+)['"]([^'"]+)['"]""", re.MULTILINE)
FE_TARGET = re.compile(r"(^|/)(components/(whatsapp|solutions)(/|$)|services/(whatsappApi|solutionsApi)$|pages/(WhatsApp\w*|\w*Solutions?\w*Page)$)")

# Feature-owned code: moves out with the feature, so its imports are not core edges.
FEATURE_PATHS = (
    "huf/ai/whatsapp/",
    "huf/ai/solutions/",
    "huf/ai/gateway_adapters/whatsapp",
    "huf/ai/tools/whatsapp.py",
    "huf/huf/doctype/whatsapp_",
    "huf/huf/doctype/solution/",
    "huf/patches/",
    "huf/testing/fake_graph_server.py",
    "frontend/src/components/whatsapp/",
    "frontend/src/components/solutions/",
    "frontend/src/services/whatsappApi.ts",
    "frontend/src/services/solutionsApi.ts",
    "frontend/src/pages/WhatsApp",
    "frontend/src/pages/Solution",
    "frontend/src/pages/NewSolution",
)
SKIP_DIRS = {"node_modules", "__pycache__", "tests", "test", "__tests__", "dist", "e2e"}
SKIP_SUFFIXES = (".d.ts", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx", "_test.py")

DEFAULT_BASELINE = Path(__file__).resolve().parent / "baselines" / "core_boundary.json"


def is_core(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    if name.startswith("test_") or name.endswith(SKIP_SUFFIXES):
        return False
    if any(part in SKIP_DIRS for part in rel.split("/")[:-1]):
        return False
    return not rel.startswith(FEATURE_PATHS)


def _module_of(rel: str) -> str:
    return rel[:-3].replace("/", ".").removesuffix(".__init__")


def py_edges(rel: str, source: str):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    mod = _module_of(rel)
    pkg = mod if rel.endswith("__init__.py") else mod.rsplit(".", 1)[0]
    out = set()
    for node in ast.walk(tree):
        mods = []
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parts = pkg.split(".")
                parts = parts[: len(parts) - (node.level - 1)] if node.level > 1 else parts
                base = ".".join(parts + ([base] if base else []))
            if PY_TARGET.match(base):
                mods = [base]
            else:  # e.g. "from huf.ai import whatsapp"
                mods = [f"{base}.{a.name}" for a in node.names]
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            mods = [m.group(0) for m in PY_STRING.finditer(node.value)]
        for m in mods:
            if m and PY_TARGET.match(m):
                out.add(m)
    return out


def _resolve_fe(rel: str, spec: str) -> str:
    """Map '@/x' and './x' specifiers to a path under src/ so relative imports are caught."""
    if spec.startswith("@/"):
        return spec[2:]
    if spec.startswith("."):
        parts = rel.split("/")[2:-1]  # drop frontend/src and the file name
        for seg in spec.split("/"):
            if seg == "..":
                parts = parts[:-1]
            elif seg not in (".", ""):
                parts.append(seg)
        return "/".join(parts)
    return spec


def fe_edges(rel: str, source: str):
    out = set()
    for spec in FE_IMPORT.findall(source):
        target = _resolve_fe(rel, spec).removesuffix(".ts").removesuffix(".tsx")
        if FE_TARGET.search(target):
            out.add(target)
    return out


def scan(root: Path):
    """Return sorted list of 'file -> target' edge strings."""
    edges = set()
    for base, exts, fn in (("huf", {".py"}, "py"), ("frontend/src", {".ts", ".tsx"}, "fe")):
        top = root / base
        if not top.is_dir():
            continue
        for p in top.rglob("*"):
            if not p.is_file() or p.suffix not in exts:
                continue
            rel = p.relative_to(root).as_posix()
            if not is_core(rel):
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            found = py_edges(rel, text) if fn == "py" else fe_edges(rel, text)
            edges.update(f"{rel} -> {t}" for t in found)
    return sorted(edges)


def load_baseline(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text()).get("edges", [])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--list", action="store_true", help="list current edges")
    ap.add_argument("--update", action="store_true", help="rewrite baseline (decreases only)")
    ap.add_argument("--force", action="store_true", help="with --update, allow increases")
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    args = ap.parse_args(argv)

    edges = scan(args.root)

    if args.list:
        for e in edges:
            print("  " + e)
        print(f"{len(edges)} core -> feature edges")
        return 0

    old = load_baseline(args.baseline)

    if args.update:
        added = sorted(set(edges) - set(old or []))
        if old is not None and added and not args.force:
            print("Refusing to raise the baseline (baselines only decrease):")
            for e in added:
                print("  " + e)
            print("Route the call through a gateway adapter capability, or pass --force with owner approval.")
            return 1
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(json.dumps({
            "_comment": "Generated by scripts/check_core_boundary.py --update. Entries may only disappear.",
            "count": len(edges),
            "edges": edges,
        }, indent=2) + "\n")
        print(f"Baseline written: {len(edges)} core -> feature edges.")
        return 0

    if old is None:
        print(f"No baseline at {args.baseline}; run with --update to create it.")
        return 1
    added = sorted(set(edges) - set(old))
    removed = sorted(set(old) - set(edges))
    for e in removed:
        print(f"note: edge gone, run --update to drop it: {e}")
    if added:
        print("Core boundary guard failed: new core -> WhatsApp/Solutions dependencies:")
        for e in added:
            print("  " + e)
        print("Core must reach feature code through the gateway adapter / feature registry, "
              "not by importing it (see scripts/README.md).")
        return 1
    print(f"core-boundary OK ({len(edges)} baselined edges, {len(removed)} removable)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
