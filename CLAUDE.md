# CLAUDE.md

This file previously duplicated the project architecture description now
maintained in `AGENTS.md` and `docs/architecture/`. Nothing in it was
actually Claude-specific, so it has been reduced to a pointer.

For everything about this repo — project overview, repo map, tech stack,
dev commands, code style, DocTypes, architecture, security invariants, and
validation commands — start at:

- **`AGENTS.md`** (repo root) — compact router into the docs below
- **`docs/context/README.md`** — index of architecture and reference docs
- **`docs/architecture/`** — agent runtime, tools, knowledge, memory, MCP,
  flows, execution, apps, data tables, security, frontend
- **`docs/reference/doctypes.generated.md`**, **`docs/reference/tools.generated.md`**

There is currently no Claude-specific guidance beyond what AGENTS.md
already covers. If you discover a genuinely Claude Code-specific
convention (tool usage, workflow quirk), add it here — don't re-duplicate
general project context.
