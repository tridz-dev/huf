# create_session.jsonl — Codex CLI

- **Status:** REAL (live captured run)
- **CLI version:** `codex-cli 0.144.6`
- **Auth:** `codex login status` → "Logged in using ChatGPT" (subscription/ChatGPT plan auth, not API key)
- **Exact command run:**
  ```
  codex exec --json --skip-git-repo-check "Say hello and reply with exactly one word: HELLO"
  ```
  (run inside `/tmp/codex_ws`, a freshly `git init`-ed empty scratch repo; `--skip-git-repo-check` was needed because codex refused to run in an untrusted/non-git directory otherwise — see gotcha below)
- **Confirms PLAN.md §18's assumed JSONL event shape:** `thread.started` carries `thread_id` (the resumable session identifier — analogous to Claude's `session_id`), followed by `turn.started`, `item.completed` events, and a final `turn.completed` with a `usage` object (`input_tokens`, `cached_input_tokens`, `output_tokens`, `reasoning_output_tokens`).
- **Unexpected event not in the plan's assumed list:** an `item.completed` with `"type":"error"` appeared mid-turn (`"Exceeded skills context budget..."`) — this is a **non-fatal warning-as-item**, not a turn failure; the turn still completed successfully with the correct answer. The adapter must NOT treat every `item` of `type: "error"` as a fatal provider error; it must check whether `turn.completed` (success) or `turn.failed` follows.
- **Sanitization:** stderr noise from this run (skill-loading errors referencing real home-directory skill file paths) was stripped entirely from this fixture — only the JSONL stdout stream is kept here. See `create_session.stderr_noise.meta.md` note below (not persisted as a separate fixture; noted for awareness only).
- **Gotcha for adapter design:** by default `codex exec` in a directory Codex doesn't consider "trusted" fails fast with `Not inside a trusted directory and --skip-git-repo-check was not specified.` before even reaching the model. HUF's Codex adapter will need either a pre-trusted working directory, `--skip-git-repo-check`, or `-C <dir>` pointed at a controlled workspace — this directly touches PLAN.md §18.1's "controlled, possibly empty workspace" requirement.
