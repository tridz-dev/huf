# resume_turn.json — Claude Code CLI

- **Status:** REAL (live captured run)
- **CLI version:** `2.1.281 (Claude Code)`
- **Exact command run:**
  ```
  claude -p "What was the exact word I told you to reply with in the previous message? Answer in one word." \
    --output-format json --resume f50fa1d9-1f4f-4449-97b4-99aca3c6bbc7
  ```
  (session ID from `create_session.json` in this same directory)
- **Confirms:** `--resume <session-id>` combined with `-p`/`--output-format json` continues context — the model correctly answered "HELLO", proving it recalled turn 1 despite receiving only the new prompt text on this invocation.
- **Notes:** `session_id` in the response is unchanged (same UUID), confirming resume does not mint a new session ID by default (that only happens with `--fork-session`, per `claude --help`). Usage/cost fields accumulate cache-read tokens from the prior turn's context (`cache_read_input_tokens: 22884`), which is useful for HUF cost accounting across a resumed multi-turn conversation.
