#!/usr/bin/env python3
"""
Guardrail: keep workspace/agent working files out of this repository.

Plans, findings, progress notes, run logs and scratch scripts belong in the
workspace track (huf_workspace_v2), never in the product repo. This fails when a
tracked file sits outside the allowed top-level entries or matches a forbidden
pattern.

Usage:
    python scripts/check_repo_layout.py            # checks `git ls-files`
    python scripts/check_repo_layout.py a b c      # checks the given paths
"""

import fnmatch
import subprocess
import sys

ALLOWED_TOP_LEVEL = {
    ".dockerignore", ".editorconfig", ".env.example", ".eslintrc", ".github", ".gitignore",
    ".mailmap", ".pre-commit-config.yaml", ".semgrep.yml", "AGENTS.md", "CITATION.cff",
    "CLAUDE.md", "DESIGN.md", "LICENSE", "README.md", "api-docs", "docker", "docs", "frontend",
    "CONTRIBUTING.md", "huf", "package.json", "pyproject.toml", "scripts", "yarn.lock",
}

FORBIDDEN = [
    "*/progress/*.md", "progress/*.md", "*SWARM_STATE*", "*OPUS_REVIEW*", "*ACTION_LIST*",
    "*live.env", "*.log", "*/__pycache__/*", "*.pyc",
    "Tracks/*", "*/Tracks/*", "*/findings/*", "*FINDINGS*.md", "*-todo.md", "*_TODO.md",
    "*SALVAGE*.md", "*PLAN.md", "*CONTEXT.md",
]



def main() -> int:
    paths = sys.argv[1:] or subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    bad = []
    for p in paths:
        top = p.split("/", 1)[0]
        if top not in ALLOWED_TOP_LEVEL:
            bad.append((p, f"top-level '{top}' is not allowed in this repo"))
        elif any(fnmatch.fnmatch(p, pat) for pat in FORBIDDEN) and not p.startswith("frontend/"):
            bad.append((p, "looks like a workspace/agent working file"))
    if not bad:
        return 0
    print("Workspace/working files must live in the workspace track, not in this repo:")
    for p, why in bad:
        print(f"  {p}  ({why})")
    print("Move them to workspace/Tracks/<Track>/ and update ALLOWED_TOP_LEVEL only for real product dirs.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
