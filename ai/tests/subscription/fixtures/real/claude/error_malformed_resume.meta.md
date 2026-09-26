# error_malformed_resume.txt — Claude Code CLI

- **Status:** REAL (live captured run)
- **CLI version:** `2.1.281 (Claude Code)`
- **Exact command run:**
  ```
  claude -p "hi" --output-format json --resume "not-a-real-session-id-000"
  ```
- **Observed behavior:** exit code 1; error is a **plain-text stderr message**, NOT JSON, even though `--output-format json` was requested. This is important for the adapter's error-parsing path: it cannot assume all failure output from `claude -p` is JSON-shaped — it must fall back to treating non-JSON stderr as a raw error string.
- **Message is deterministic/parseable**: contains the literal substrings "not a UUID" and "does not match any session title" — an adapter could pattern-match these to classify "resume target not found" vs. other failure classes.
