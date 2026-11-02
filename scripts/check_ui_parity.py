#!/usr/bin/env python3
"""
Guard: UI parity. Anything a user can configure or do through the backend must have a React UI
counterpart.

Fields   For each doctype in SCOPED_DOCTYPES (ratchet this list outward), every user-editable field
         (not a Section/Column/Tab Break, not hidden, not read_only) must have its exact fieldname
         appear in a non-test file under frontend/src/components, frontend/src/pages or a form-schema
         file. Services alone do not count.
Endpoints Every @frappe.whitelist function under huf/ai/gateways/** must be referenced (dotted path
         or function name) by a frontend/src/services/** file that is imported by a non-test file
         under components/ or pages/.

Exemptions live in scripts/baselines/ui_parity_exemptions.json:
  {"<doctype>.<field>" | "<module>.<fn>": {"reason", "kind": desk-only|system|webhook|planned,
                                           "owner", "expires": optional YYYY-MM-DD}}
Never exempt a user-facing feature to silence the guard; pick the kind accurately.

Fails on: uncovered and not exempt; stale exemption (now covered); missing reason / bad kind;
planned exemption past its expiry.

Usage:
    python3 scripts/check_ui_parity.py [--list] [--emit out.json]
"""

import argparse
import ast
import datetime
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_whitelist as cw  # noqa: E402

SCOPED_DOCTYPES = ["gateway", "teams_gateway_settings", "gateway_binding", "gateway_identity_link"]
ENDPOINT_ROOT = "huf/ai/gateways"
LAYOUT_TYPES = {"Section Break", "Column Break", "Tab Break"}
KINDS = {"desk-only", "system", "webhook", "planned"}
UI_DIRS = ("frontend/src/components", "frontend/src/pages")
SCHEMA_RE = re.compile(r"(schema|formschema|form-schema)", re.I)
DEFAULT_EXEMPTIONS = Path(__file__).resolve().parent / "baselines" / "ui_parity_exemptions.json"
SRC_EXT = {".ts", ".tsx", ".js", ".jsx"}


def is_test(p):
    n = p.name
    return ".test." in n or ".spec." in n or "__tests__" in p.parts or "tests" in p.parts


def src_files(root, base):
    d = root / base
    if not d.is_dir():
        return []
    return [p for p in d.rglob("*") if p.suffix in SRC_EXT and p.is_file() and not is_test(p)]


def required_fields(root, doctypes):
    out = {}
    for dt in doctypes:
        for j in (root / "huf/huf/doctype" / dt).glob("*.json"):
            if j.stem != dt:
                continue
            for f in json.loads(j.read_text()).get("fields", []):
                if f.get("fieldtype") in LAYOUT_TYPES or f.get("hidden") or f.get("read_only"):
                    continue
                out[f"{dt}.{f['fieldname']}"] = f.get("fieldtype", "")
    return out


def ui_text(root):
    files = []
    for d in UI_DIRS:
        files += src_files(root, d)
    files += [p for p in src_files(root, "frontend/src") if SCHEMA_RE.search(p.name)]
    return "\n".join(p.read_text(errors="ignore") for p in set(files))


def endpoints(root):
    found = {}
    base = root / ENDPOINT_ROOT
    for p in sorted(base.rglob("*.py")):
        if cw.SKIP_DIRS & set(p.parts):
            continue
        tree = ast.parse(p.read_text())
        mod = ".".join(p.relative_to(root).with_suffix("").parts)
        if mod.endswith(".__init__"):
            mod = mod[: -len(".__init__")]
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and cw._whitelist_decorator(n):
                found[f"{mod}.{n.name}"] = (mod, n.name)
    return found


def covered_endpoints(root, eps):
    services = {p: p.read_text(errors="ignore") for p in src_files(root, "frontend/src/services")}
    ui = [p.read_text(errors="ignore") for d in UI_DIRS for p in src_files(root, d)]
    imported = {}
    for p in services:
        pat = re.compile(r"from\s+['\"][^'\"]*/" + re.escape(p.stem) + r"['\"]")
        imported[p] = any(pat.search(t) for t in ui)
    done = set()
    for key, (mod, fn) in eps.items():
        fnre = re.compile(r"\b" + re.escape(fn) + r"\b")
        for p, t in services.items():
            if imported[p] and (key in t or fnre.search(t)):
                done.add(key)
                break
    return done


def evaluate(root, exemptions):
    reqf = required_fields(root, SCOPED_DOCTYPES)
    text = ui_text(root)
    cov = {k for k in reqf if re.search(r"\b" + re.escape(k.split(".", 1)[1]) + r"\b", text)}
    eps = endpoints(root)
    cov |= covered_endpoints(root, eps)
    universe = set(reqf) | set(eps)
    today = datetime.date.today()
    errors, uncovered = [], []
    for k in sorted(universe - cov):
        if k not in exemptions:
            uncovered.append(k)
    for k, e in sorted(exemptions.items()):
        if not str(e.get("reason", "")).strip():
            errors.append(f"exemption {k}: missing reason")
        if e.get("kind") not in KINDS:
            errors.append(f"exemption {k}: kind must be one of {sorted(KINDS)}")
        if not str(e.get("owner", "")).strip():
            errors.append(f"exemption {k}: missing owner")
        if k in cov:
            errors.append(f"exemption {k}: stale, now covered by UI; remove it")
        elif k not in universe:
            errors.append(f"exemption {k}: stale, no such field/endpoint in scope; remove it")
        if e.get("kind") == "planned" and e.get("expires"):
            if datetime.date.fromisoformat(e["expires"]) < today:
                errors.append(f"exemption {k}: planned exemption expired {e['expires']}")
    return reqf, uncovered, errors


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--exemptions", type=Path, default=DEFAULT_EXEMPTIONS)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--emit", type=Path, help="write required fields per provider as JSON")
    ap.add_argument("--update", action="store_true", help="ignored (baseline is hand-edited)")
    args = ap.parse_args(argv)
    ex = {}
    if args.exemptions.exists():
        ex = {k: v for k, v in json.loads(args.exemptions.read_text()).items() if not k.startswith("_")}
    reqf, uncovered, errors = evaluate(args.root, ex)
    if args.emit:
        prov = {}
        for k in reqf:
            dt, f = k.split(".", 1)
            if k not in ex:
                prov.setdefault(dt, []).append(f)
        args.emit.write_text(json.dumps(prov, indent=2, sort_keys=True) + "\n")
    if uncovered or errors:
        print("ui-parity: FAIL")
        for k in uncovered:
            print(f"  uncovered: {k}  (add UI, or an accurate exemption)")
        for e in errors:
            print(f"  {e}")
        return 1
    print(f"ui-parity: OK ({len(reqf)} fields, {len(ex)} exemptions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
