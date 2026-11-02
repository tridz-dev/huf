#!/usr/bin/env python3
"""
Guard: whitelisted endpoint hygiene (Backend API standard, Phase E / G4).

Static (ast) scan of huf/**/*.py. For every function decorated with ``frappe.whitelist`` it
records three rule violations:

  guest_unverified   allow_guest=True, and neither the body nor a same-module function it calls
                     (call graph depth 1) references signature/HMAC verification
                     (names matching VERIFY_PATTERN, e.g. verify_*, hmac, compare_digest).
  no_permission      not allow_guest, and neither the body nor a same-module function it calls
                     (depth 1) calls a recognised permission check (PERMISSION_CALLS /
                     PERMISSION_PATTERNS below). Guest endpoints are covered by the rule above.
  mutating_get       the body or a depth-1 callee calls a mutation (MUTATING_ATTRS: set_value,
                     insert, save, delete_doc...) while ``methods`` does not restrict the
                     endpoint to non-GET verbs (no ``methods=`` means GET is allowed).

All three are heuristics: they look at call NAMES only, they do not prove the check runs before
the first read, and a call hidden in an imported helper is only seen when its name matches. Add
new recognised helper names to the lists below rather than silencing a finding.

The baseline (scripts/baselines/whitelist.json) holds the current count per file per rule.
A count may not rise (this also catches new files); it only ever shrinks.

Usage:
    python3 scripts/check_whitelist.py            # check
    python3 scripts/check_whitelist.py --list     # print every offender per rule
    python3 scripts/check_whitelist.py --update   # rewrite baseline (decreases only)
    python3 scripts/check_whitelist.py --update --force   # allow increases
"""

import argparse
import ast
import json
import re
import sys
from pathlib import Path

RULES = ("guest_unverified", "no_permission", "mutating_get")

# ---- configurable recognition lists -------------------------------------------------------------
# Matched against the last component of a call name (``frappe.has_permission`` -> ``has_permission``).
PERMISSION_CALLS = {
    "has_permission", "check_permission", "has_website_permission", "only_for", "has_role",
    "get_roles", "has_capability", "require_permission", "has_app_permission",
    "validate_permission", "check_app_permission",
}
PERMISSION_PATTERNS = [
    r"^_?require_\w+",           # require_admin, _require_admin, require_capability
    r"^_?can_\w+",               # can_manage_integrations
    r"^_can_manage\w*",
    r"^_gateway_\w*_allowed$",   # _gateway_read_allowed / _gateway_write_allowed
    r"^_?is_admin$",
    r"^_?(check|ensure|assert|validate)_\w*(perm|access|admin|authori[sz]|allowed)\w*",
    r"^_?\w*_(permitted|allowed|readable|writable)$",
    r"^_has_\w*permission$",
    r"^_?get_current_user\w*",
    r"^_?authenticate\w*",
]
VERIFY_PATTERN = r"(verify|hmac|signature|compare_digest|check_signature|validate_webhook|constant_time)"
# Attribute names of calls that mutate data (list.insert is excluded by the arity check below).
MUTATING_ATTRS = {
    "set_value", "set_single_value", "insert", "save", "submit", "cancel", "delete", "delete_doc",
    "db_set", "db_insert", "db_update", "rename_doc", "save_file", "bulk_update", "add_comment",
    "insert_many", "update_doc", "new_doc_insert",
}
NON_GET_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

SCAN_ROOT = "huf"
SKIP_DIRS = {"__pycache__", "node_modules", "tests", "test", "fixtures"}
DEFAULT_BASELINE = Path(__file__).resolve().parent / "baselines" / "whitelist.json"

_PERM_RE = [re.compile(p) for p in PERMISSION_PATTERNS]
_VERIFY_RE = re.compile(VERIFY_PATTERN, re.I)


# ---- ast helpers ---------------------------------------------------------------------------------
def _dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _whitelist_decorator(fn):
    """Return the whitelist decorator call/name node of ``fn`` or None."""
    for dec in fn.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if _dotted(target).split(".")[-1] == "whitelist":
            return dec
    return None


def _decorator_options(dec):
    guest, methods = False, None
    if isinstance(dec, ast.Call):
        for kw in dec.keywords:
            if kw.arg == "allow_guest":
                guest = isinstance(kw.value, ast.Constant) and kw.value.value is True
            elif kw.arg == "methods":
                if isinstance(kw.value, (ast.List, ast.Tuple, ast.Set)):
                    methods = [e.value.upper() for e in kw.value.elts
                               if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                elif isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    methods = [kw.value.value.upper()]
                else:
                    methods = ["?"]  # dynamic: treat as restricted
    return guest, methods


def _calls(fn):
    """Yield (last_name, dotted_name, call_node) for every call, and bare names read, in ``fn``."""
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            dotted = _dotted(node.func)
            if dotted:
                yield dotted.split(".")[-1], dotted, node


def _names(fn):
    """All identifiers and attribute names referenced in ``fn`` (for verification references)."""
    out = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
    return out


def is_permission_call(name):
    return name in PERMISSION_CALLS or any(r.match(name) for r in _PERM_RE)


def is_mutation(name, node):
    if name not in MUTATING_ATTRS or not isinstance(node.func, ast.Attribute):
        return False
    if name == "insert" and len(node.args) > 1:  # list.insert(i, x)
        return False
    return True


def _facts(fn):
    calls = list(_calls(fn))
    return {
        "perm": any(is_permission_call(n) for n, _, _ in calls),
        "verify": any(_VERIFY_RE.search(n) for n in _names(fn)),
        "mutates": any(is_mutation(n, c) for n, _, c in calls),
        "callees": {n for n, d, _ in calls if "." not in d or d.startswith("self.")},
    }


def scan_file(path: Path, rel: str):
    """Return a list of dicts {file, name, line, rules:[...]} for whitelisted functions with findings."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
    except (SyntaxError, UnicodeDecodeError):
        return [], 0
    funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    facts = {}
    for f in funcs:  # last definition wins; good enough for depth 1 lookups
        facts[f.name] = _facts(f)
    found, total = [], 0
    for fn in funcs:
        dec = _whitelist_decorator(fn)
        if dec is None:
            continue
        total += 1
        guest, methods = _decorator_options(dec)
        own = facts.get(fn.name) or _facts(fn)
        own = _facts(fn)
        callee_facts = [facts[c] for c in own["callees"] if c in facts and c != fn.name]

        def any_of(key):
            return own[key] or any(cf[key] for cf in callee_facts)

        rules = []
        if guest and not any_of("verify"):
            rules.append("guest_unverified")
        if not guest and not any_of("perm"):
            rules.append("no_permission")
        restricted = methods is not None and all(m in NON_GET_METHODS or m == "?" for m in methods)
        if any_of("mutates") and not restricted:
            rules.append("mutating_get")
        if rules:
            found.append({"file": rel, "name": fn.name, "line": fn.lineno, "rules": rules})
    return found, total


def scan(root: Path):
    findings, whitelisted = [], 0
    top = root / SCAN_ROOT
    if not top.is_dir():
        return findings, whitelisted
    for p in sorted(top.rglob("*.py")):
        rel = p.relative_to(root)
        if p.name.startswith("test_") or any(part in SKIP_DIRS for part in rel.parts[:-1]):
            continue
        f, n = scan_file(p, rel.as_posix())
        findings += f
        whitelisted += n
    return findings, whitelisted


def counts(findings):
    out = {r: {} for r in RULES}
    for f in findings:
        for r in f["rules"]:
            out[r][f["file"]] = out[r].get(f["file"], 0) + 1
    return out


def totals(cnt):
    return {r: sum(cnt[r].values()) for r in RULES}


def load_baseline(path: Path):
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return {r: data.get("rules", {}).get(r, {}) for r in RULES}


def increases(old, new):
    out = []
    for r in RULES:
        for k, v in new[r].items():
            if v > old[r].get(k, 0):
                out.append(f"{r} {k}: {old[r].get(k, 0)} -> {v}")
    return out


def build_baseline(cnt, whitelisted):
    return {
        "_comment": "Generated by scripts/check_whitelist.py --update. Counts may only shrink or disappear.",
        "whitelisted_functions": whitelisted,
        "totals": totals(cnt),
        "rules": {r: dict(sorted(cnt[r].items())) for r in RULES},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--list", action="store_true", help="print offenders per rule")
    ap.add_argument("--update", action="store_true", help="rewrite baseline (decreases only)")
    ap.add_argument("--force", action="store_true", help="with --update, allow increases")
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    args = ap.parse_args(argv)

    findings, whitelisted = scan(args.root)
    cnt = counts(findings)

    if args.list:
        for r in RULES:
            rows = [f for f in findings if r in f["rules"]]
            print(f"{r} ({len(rows)}):")
            for f in sorted(rows, key=lambda x: (x["file"], x["line"])):
                print(f"  {f['file']}:{f['line']} {f['name']}")
        return 0

    if args.update:
        old = load_baseline(args.baseline)
        if old is not None and not args.force:
            bad = increases(old, cnt)
            if bad:
                print("Refusing to raise the baseline (baselines only decrease):")
                for b in bad:
                    print("  " + b)
                print("Fix the code, or pass --force with owner approval.")
                return 1
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(json.dumps(build_baseline(cnt, whitelisted), indent=2) + "\n")
        t = totals(cnt)
        print(f"Baseline written: {whitelisted} whitelisted functions; "
              + ", ".join(f"{r}={t[r]}" for r in RULES))
        return 0

    base = load_baseline(args.baseline)
    if base is None:
        print(f"No baseline at {args.baseline}; run with --update to create it.")
        return 1
    errors, stale = [], []
    for r in RULES:
        for rel, n in sorted(cnt[r].items()):
            allowed = base[r].get(rel, 0)
            if n > allowed:
                names = ", ".join(f["name"] for f in findings if f["file"] == rel and r in f["rules"])
                errors.append(f"{rel}: {r} {n} (baseline {allowed}): {names}")
        for rel, allowed in base[r].items():
            if cnt[r].get(rel, 0) < allowed:
                stale.append(f"{r} {rel}")
    for s in stale:
        print(f"note: {s} improved; run --update to lower the baseline")
    if errors:
        print("Whitelist guard failed:")
        for e in errors:
            print("  " + e)
        print("Check permission first (huf/ai/api_support.py require_permission), verify a signature on "
              "guest endpoints, and use methods=[\"POST\"] for mutations.")
        return 1
    t = totals(cnt)
    print(f"whitelist OK ({whitelisted} whitelisted functions; "
          + ", ".join(f"{r}={t[r]}" for r in RULES) + ")")
    return 0


if __name__ == "__main__":
    sys.exit(main())
