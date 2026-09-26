# resume_turn.jsonl — Codex CLI

- **Status:** REAL (live captured run)
- **CLI version:** `codex-cli 0.144.6`
- **Exact command run:**
  ```
  codex exec resume --json 01a0da32-e450-7691-a8e5-579223d9a47a \
    "What was the exact word I told you to reply with in the previous message? Answer in one word."
  ```
  (thread id from `create_session.jsonl` in this same directory; run from the same `/tmp/codex_ws` working directory as the original session)
- **Confirms context continuity:** model correctly answered "HELLO", proving `codex exec resume <thread_id> <prompt>` restores prior turn context.
- **Confirms `thread_id` is stable across resume** (unchanged in the `thread.started` event).
- **Usage accumulates:** `cached_input_tokens: 27136` reflects the prior turn's context being replayed/cached — relevant for HUF cost accounting across resumed turns.
- **Gotcha:** resume was run from the *same* working directory as the original `codex exec` call. PLAN.md §18.1 flags "resume does not accidentally depend on a repository state HUF does not control" as something to verify — this fixture does NOT prove resume works from a different cwd; that must be tested separately before shipping (see summary doc).
