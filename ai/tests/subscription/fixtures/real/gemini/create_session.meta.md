# create_session.txt — Gemini CLI

- **Status:** SYNTHETIC (from docs; deliberately contains no fabricated JSON body — see file for why)
- **CLI version:** unknown / not installed
- **MUST re-verify against a live authenticated `gemini` CLI before ship:** the entire
  `--output-format json` response schema for a single non-interactive turn (field names,
  whether session id appears in the body vs. only discoverable via `--list-sessions`,
  whether usage/token accounting appears per-turn). This is the single highest-priority
  gap in the Gemini adapter spike — everything else in PLAN.md §17 is unverifiable until
  this shape is captured live.
