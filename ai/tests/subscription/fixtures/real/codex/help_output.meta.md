# help_output_exec.txt / help_output_top.txt — Codex CLI

- **Status:** REAL (live captured run)
- **CLI version:** `codex-cli 0.144.6`
- **Exact commands run:** `codex exec --help` (-> help_output_exec.txt), `codex --help` (-> help_output_top.txt)
- **Relevant flags confirmed present:**
  - Non-interactive: `codex exec [PROMPT]`, reads stdin if no prompt/`-`
  - Structured output: `--json` (JSONL events to stdout), `--output-schema <FILE>` (JSON Schema for final response), `--output-last-message <FILE>`
  - Session resume: `codex exec resume [SESSION_ID] [PROMPT]`, `--last` (most recent session), `--all` (disable cwd filtering — confirms sessions are cwd-scoped by default, same family of concern as Gemini's project-hash scoping in PLAN.md §17.1)
  - Image input: `-i, --image <FILE>...` — "Optional image(s) to attach to the initial prompt" — present on BOTH `codex exec` and `codex exec resume`, confirming PLAN.md §18's "image support elsewhere in the CLI" extends to the resume path too (this directly answers PLAN.md §18.1's open question "does image input work through the chosen noninteractive resume mode" — answer: yes, a flag exists; behavior itself was not exercised in this spike per instructions).
  - MCP: `codex mcp` (manage external MCP servers), `codex mcp-server` (run Codex itself as an MCP server, unrelated direction)
  - Sandbox/approval: `-s/--sandbox <read-only|workspace-write|danger-full-access>`, `--dangerously-bypass-approvals-and-sandbox` — this is Codex's tool-restriction knob, relevant to PLAN.md §18.1's "native write/command tools can be constrained enough" requirement.
  - Working directory: `-C/--cd <DIR>`, `--add-dir <DIR>`, `--skip-git-repo-check` — directly relevant to the "controlled, possibly empty workspace" requirement and to the trusted-directory gotcha observed in this spike.
- **No dedicated auth-status flag found in `codex exec --help`** — auth status was checked via `codex login status`, a separate top-level subcommand, not an `exec` flag.
