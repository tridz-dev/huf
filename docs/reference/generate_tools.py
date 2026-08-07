#!/usr/bin/env python3
"""Generate docs/reference/tools.generated.md from the live integration tool registry.

Regenerate whenever tools change:
    python3 docs/reference/generate_tools.py

Source of truth is huf/ai/tools/_registry.py:ALL_INTEGRATION_TOOLS — this covers the
per-integration tools (Slack, GitHub, Google, ERPNext, ...). It does NOT cover the small set of
core/standard tools re-exported from huf/ai/sdk_tools.py (ocr_document, generate_image,
generate_audio, transcribe_audio) — those are documented narratively in
docs/architecture/tools-and-integrations.md since they need behavioral description, not just a
parameter table.

Do not hand-edit the .generated.md output; fix this script or the registry instead.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "huf" / "ai" / "tools" / "_registry.py"
OUT = ROOT / "docs" / "reference" / "tools.generated.md"


def load_registry():
    spec = importlib.util.spec_from_file_location("_registry", REGISTRY_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ALL_INTEGRATION_TOOLS


def render(tools):
    by_category = {}
    for t in tools:
        by_category.setdefault(t.get("category", "Uncategorized"), []).append(t)

    lines = [
        "# Integration tool reference (generated)",
        "",
        "**Generated file — do not hand-edit.** Regenerate with "
        "`python3 docs/reference/generate_tools.py`. Source of truth is "
        "`huf/ai/tools/_registry.py` (`ALL_INTEGRATION_TOOLS`); if this file and the registry "
        "ever disagree, the registry wins and this file is stale — regenerate it.",
        "",
        f"{len(tools)} registered integration tools across {len(by_category)} categories as of "
        "this generation. Core/standard tools (ocr_document, generate_image, generate_audio, "
        "transcribe_audio — re-exported from `huf/ai/sdk_tools.py`) are documented separately in "
        "[`../architecture/tools-and-integrations.md`](../architecture/tools-and-integrations.md).",
        "",
    ]
    for category in sorted(by_category):
        lines.append(f"## {category}")
        lines.append("")
        for t in by_category[category]:
            lines.append(f"### `{t['tool_name']}`")
            lines.append("")
            lines.append(t.get("description", "").strip())
            lines.append("")
            lines.append(f"- **Function**: `{t.get('function_path', '')}`")
            if t.get("service"):
                lines.append(f"- **Service**: `{t['service']}`")
            params = t.get("parameters", [])
            if params:
                lines.append("- **Parameters**:")
                lines.append("")
                lines.append("  | Field | Type | Required | Description |")
                lines.append("  |---|---|---|---|")
                for p in params:
                    req = "yes" if p.get("required") else ""
                    desc = (p.get("description") or "").replace("\n", " ").replace("|", "\\|")
                    lines.append(f"  | `{p.get('fieldname', '')}` | {p.get('type', '')} | {req} | {desc} |")
            lines.append("")
    return "\n".join(lines)


def main():
    tools = load_registry()
    if not tools:
        print("no tools found — check REGISTRY_PATH", file=sys.stderr)
        sys.exit(1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(tools))
    print(f"wrote {OUT} ({len(tools)} tools)")


if __name__ == "__main__":
    main()
