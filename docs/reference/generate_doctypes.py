#!/usr/bin/env python3
"""Generate docs/reference/doctypes.generated.md from the live DocType JSON schemas.

Regenerate whenever DocTypes change:
    python3 docs/reference/generate_doctypes.py

Source of truth is huf/huf/doctype/*/*.json — this script only reads, never edits schemas.
Do not hand-edit the .generated.md output; fix this script or the schema instead.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCTYPE_DIR = ROOT / "huf" / "huf" / "doctype"
OUT = ROOT / "docs" / "reference" / "doctypes.generated.md"

SKIP_FIELDTYPES = {"Column Break", "Section Break", "Tab Break"}


def load_doctypes():
    entries = []
    for json_path in sorted(DOCTYPE_DIR.glob("*/*.json")):
        try:
            data = json.loads(json_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict) or data.get("doctype") != "DocType":
            continue
        entries.append((json_path, data))
    return entries


def field_rows(data):
    rows = []
    for f in data.get("fields", []):
        if f.get("fieldtype") in SKIP_FIELDTYPES:
            continue
        fieldname = f.get("fieldname", "")
        fieldtype = f.get("fieldtype", "")
        options = f.get("options") or ""
        reqd = "required" if f.get("reqd") else ""
        desc = (f.get("description") or f.get("label") or "").replace("\n", " ").replace("|", "\\|")
        target = f" -> {options}" if fieldtype in ("Link", "Table", "Table MultiSelect", "Select") and options else ""
        rows.append((fieldname, fieldtype + target, reqd, desc))
    return rows


def render(entries):
    lines = [
        "# DocType reference (generated)",
        "",
        "**Generated file — do not hand-edit.** Regenerate with "
        "`python3 docs/reference/generate_doctypes.py`. Source of truth is "
        "`huf/huf/doctype/*/*.json`; if this file and the schema ever disagree, the schema wins "
        "and this file is stale — regenerate it.",
        "",
        f"{len(entries)} DocTypes as of this generation.",
        "",
    ]
    for json_path, data in entries:
        name = data.get("name") or json_path.parent.name
        module = data.get("module", "")
        rel = json_path.relative_to(ROOT)
        kind = []
        if data.get("istable"):
            kind.append("child table")
        if data.get("issingle"):
            kind.append("single")
        kind_str = f" ({', '.join(kind)})" if kind else ""
        lines.append(f"## {name}{kind_str}")
        lines.append("")
        lines.append(f"- **Module**: {module}")
        lines.append(f"- **Schema**: `{rel}`")
        lines.append(f"- **Naming**: {data.get('autoname') or data.get('naming_rule') or '-'}")
        lines.append("")
        rows = field_rows(data)
        if rows:
            lines.append("| Fieldname | Type | Required | Description |")
            lines.append("|---|---|---|---|")
            for fieldname, fieldtype, reqd, desc in rows:
                lines.append(f"| `{fieldname}` | {fieldtype} | {reqd} | {desc} |")
        lines.append("")
    return "\n".join(lines)


def main():
    entries = load_doctypes()
    if not entries:
        print("no doctypes found — check DOCTYPE_DIR", file=sys.stderr)
        sys.exit(1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(entries))
    print(f"wrote {OUT} ({len(entries)} doctypes)")


if __name__ == "__main__":
    main()
