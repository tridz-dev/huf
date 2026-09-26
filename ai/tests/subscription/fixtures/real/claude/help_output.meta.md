# help_output.txt — Claude Code CLI

- **Status:** REAL (live captured run)
- **CLI version:** `2.1.281 (Claude Code)`
- **Exact command run:** `claude --help`
- **Relevant flags confirmed present:**
  - Non-interactive: `-p`/`--print`
  - Structured output: `--output-format <text|json|stream-json>`, `--json-schema <schema>` (structured output schema)
  - Session resume: `-r`/`--resume [value]` (by session ID or name), `--fork-session` (resume but mint a new session ID), `--session-id <uuid>` (caller-supplied UUID for a NEW session — confirms PLAN.md §16.2's idempotency design is viable), `--continue`
  - MCP: `--mcp-config <configs...>`, `--strict-mcp-config` (confirms PLAN.md §16.3's tool-bridge plan)
  - No dedicated image/vision CLI flag was found in `--help` text itself — Claude Code accepts images via file paths/paste in prompt content, not a dedicated `--image` flag like Codex has. This should be re-verified against `code.claude.com/docs/en/headless` before the adapter assumes no image flag exists.
  - `--permission-mode`, `--model`, `--effort`, `--system-prompt`, `--no-session-persistence`, `--settings` also present.
- **Full untruncated help text saved as-is; no sanitization needed (no paths/secrets in --help output).**
