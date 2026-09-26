# help_output.txt — Gemini CLI

- **Status:** SYNTHETIC (derived from official docs, NOT a live run)
- **Reason:** `gemini` binary not found (`which gemini` -> not found) in this environment; not installed, not authenticated.
- **CLI version:** unknown (not captured; docs are from the `main` branch of github.com/google-gemini/gemini-cli as of 2026-09-26, so may be ahead of any released version)
- **Sources fetched:**
  - https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/cli-reference.md
  - https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/session-management.md
  - https://github.com/google-gemini/gemini-cli/blob/main/docs/get-started/authentication.mdx
- **MUST re-verify against a live authenticated `gemini` CLI before ship (Stage 12 / PLAN.md §75.7):**
  1. The exact `--help` text, flag names, and short-form letters (`-p`, `-o`, `-r`, `-i`) — docs prose was fetched via an AI summarizer (WebFetch), not the raw markdown; exact flag spelling could be paraphrased.
  2. Whether `--output-format json` produces a structured single-JSON-object response with fields analogous to Claude's `session_id`/`result`/`usage` — the fetched docs did NOT show an example JSON response body, only the flag's existence. PLAN.md §17 assumes this exists; it is UNCONFIRMED.
  3. Whether there is any `gemini auth status` or equivalent machine-readable auth-check command — none was found in the fetched docs; PLAN.md's adapter design needs one and may have to fall back to a side-effect probe (e.g. attempt a trivial `-p` call and inspect exit code/stderr for an auth-required error).
  4. Image/vision input flag — not found in the fetched docs at all; do not assume its absence without checking the full CLI reference file directly (only a summarized extract was retrieved here).
  5. The exact malformed-resume and auth-required error text/shape — no error examples were present in the fetched docs; the `error_malformed_resume.txt` and `auth_status.json` fixtures in this directory are speculative reconstructions only, not doc-derived, and carry the LOWEST confidence of all fixtures in this track.
