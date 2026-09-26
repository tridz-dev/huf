# auth_status.txt — Codex CLI

- **Status:** REAL (live captured run)
- **CLI version:** `codex-cli 0.144.6`
- **Exact command run:** `codex login status`
- **Observed:** plain text, NOT JSON — `"Logged in using ChatGPT"`. This differs from Claude's `auth status`, which returns structured JSON. The Codex adapter's auth-check logic cannot assume a machine-readable shape here; it must pattern-match the string (or find a `--json` variant not surfaced by this exact subcommand/version — none was found in `codex --help`/`codex exec --help`).
- **Confirms:** PLAN.md §18's "ChatGPT-based sign-in/plan usage as distinct from API-key mode" — output explicitly names "ChatGPT" as opposed to an API key.
- **Not captured:** the logged-out or API-key-mode output shape (this account is live and logged in via ChatGPT subscription; logging out was not attempted to avoid disrupting the user's environment). Flagged for re-verification before shipping.
