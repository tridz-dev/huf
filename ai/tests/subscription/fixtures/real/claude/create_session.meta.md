# create_session.json — Claude Code CLI

- **Status:** REAL (live captured run)
- **CLI version:** `2.1.281 (Claude Code)`
- **Auth:** `claude auth status` → `authMethod: "claude.ai"`, `subscriptionType: "max"` (subscription OAuth, not API key)
- **Exact command run:**
  ```
  claude -p "Say hello and reply with exactly one word: HELLO" --output-format json
  ```
  (run from a scratch `/tmp` directory, not a HUF-managed workspace)
- **Notes for the adapter:**
  - `session_id` (top-level field, snake_case) is the provider session ID to persist for resume — confirms PLAN.md §16.1's assumption that JSON result contains session metadata.
  - `result` holds the final assistant text (here just `"HELLO"`).
  - `usage` includes `cache_creation_input_tokens` / `cache_read_input_tokens` split, plus a `modelUsage` map keyed by canonical model id (`claude-opus-5-5[1m]`) with `costUSD`/`contextWindow`/`provider: "firstParty"` — useful for HUF's spend accounting, confirms subscription (non-API-key) requests still report structured cost/usage.
  - `subagent_stats`, `permission_denials`, `fast_mode_state` present even for a trivial single-turn prompt — these are always-present fields, not conditional.
  - No file paths, usernames, or secrets appeared in this output; nothing was sanitized.
