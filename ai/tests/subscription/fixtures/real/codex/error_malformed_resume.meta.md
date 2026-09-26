# error_malformed_resume.txt — Codex CLI

- **Status:** REAL (live captured run)
- **CLI version:** `codex-cli 0.144.6`
- **Exact command run:**
  ```
  codex exec resume --json 00000000-0000-0000-0000-000000000000 "hi"
  ```
  (well-formed UUID syntactically, but no such thread exists)
- **Observed behavior:** plain-text stderr error, NOT a JSONL event, despite `--json` being passed — same gotcha as Claude: error output can bypass the structured-output mode entirely. Message includes a JSON-RPC-style error code (`code -32600`, "Invalid Request" in JSON-RPC terms) embedded in plain text — Codex's internals appear to speak JSON-RPC to a local session store ("rollout").
- **Adapter implication:** pattern-match on `"no rollout found for thread id"` to classify "resume target not found," and do not assume `--json` guarantees JSON on every exit path.
- **Not yet tested:** a resume with a *malformed* (non-UUID) string rather than a well-formed-but-nonexistent UUID — the CLI's `resume` help says "UUIDs take precedence if it parses," implying a non-UUID string is treated as a thread *name* lookup instead, which would likely produce a different error shape. Flagged for re-verification (see summary doc).
