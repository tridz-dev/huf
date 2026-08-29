# frappe.log_error() argument-order cleanup

## Background

`frappe.log_error(title=None, message=None, ...)` stores `title` in a DB column
with a 140-character limit. Frappe applies a "smart swap" heuristic: if the
second positional argument contains a newline, it assumes the arguments were
passed backwards and swaps them. This heuristic only helps when the `message`
argument happens to contain a newline (e.g. `frappe.get_traceback()`).

A previous session fixed 4 call sites in `huf/ai/agent_integration.py` where
`frappe.log_error(f"<long dynamic string>", "<short static label>")` was used
without a newline in the first argument — meaning Frappe's swap never fires,
the long dynamic string is stored as `title`, and if it exceeds 140 characters
the call raises `CharacterLengthExceededError` instead of logging cleanly.

This pass found and fixed the remaining call sites across the rest of the
`huf` app with the same bug.

## Method

1. Parsed every `frappe.log_error(...)` call site in `huf/` (288 total) with a
   small paren-balanced/string-aware Python script (not a blind regex), and
   split each call's arguments.
2. Categorized each call:
   - **(a) genuinely broken** — first positional argument is a dynamic string
     (f-string, `.format()`, concatenation) with no newline literal, and the
     second positional argument looks like a short static title. Frappe's
     swap heuristic never fires here, and a sufficiently long dynamic value
     will crash the call.
   - **(b) already safe** — either a single positional argument, already using
     `title=`/`message=` keywords in the correct positions, or the dynamic
     value contains a newline (protected by Frappe's own swap heuristic, e.g.
     anything embedding `frappe.get_traceback()`).
   - **(c) ambiguous** — needs a human judgment call; listed below, left
     untouched.
3. For every (a) site, rewrote the call as
   `frappe.log_error(title="<short label>", message=f"<original dynamic string>")`,
   matching the pattern from the 4 previously-fixed sites in
   `agent_integration.py`. The title reused whatever short static label was
   already present as the second positional argument (or, for the 7 sites
   where the call passed a variable as `message` with a separately-defined
   `title` variable/default, reused those variable names directly — e.g.
   `huf/ai/ocr_engine.py`'s `_log_error(message, title)` helper).
4. Where the mechanical rewrite collapsed a call onto one line that then
   exceeded the project's 110-char line-length limit (`pyproject.toml`
   `[tool.ruff] line-length = 110`), reformatted those calls back into
   multi-line `frappe.log_error(\n\ttitle=...,\n\tmessage=...,\n)` form,
   matching each file's existing tab/space indentation style.

## Results

- **288** total `frappe.log_error(...)` call sites found in `huf/`.
- **121** fixed (114 caught by the automated dynamic-first/static-second
  pattern match, plus 7 more found by manual review of the ambiguous bucket
  that used the same backwards shape with a variable instead of an inline
  f-string: `huf/ai/ocr_engine.py:69`, `huf/ai/agent_scheduler.py:63`,
  `huf/ai/automation_scheduler.py:177`, `huf/ai/flow_api.py:735`,
  `huf/ai/app_seeding/apps_loader.py:326`, `huf/ai/skills/hooks.py:253`,
  `huf/ai/skills/importer.py:424`).
- **155** already safe, left untouched (single-arg calls, already-correct
  keyword usage, or traceback-embedding messages protected by Frappe's own
  newline swap heuristic).
- **12** left for manual review (see below) — all of these are backwards in
  spirit (`message`-like content first, `title`-like label second) but pose
  **no crash risk** today because the first positional argument is a fixed,
  short (well under 140 char) string literal, so fixing them is a style
  improvement rather than a bug fix. Not touched in this pass to keep the
  diff scoped to genuine bugs.

### Files touched (46)

46 files across `huf/ai/`, `huf/huf/doctype/`, and `huf/patches/` were edited.
Full list: `git diff --stat` on branch `fix/log-error-arg-order-cleanup`
against its base.

### Left for manual review (file:line)

All of these have both arguments as fixed string literals (no dynamic
content), so there's no `CharacterLengthExceededError` risk — but the
semantic order is `message, title` instead of `title, message`, which is
worth a human pass to confirm the swap is safe/desired stylistically:

- `huf/ai/artifact_instructions.py:151`
- `huf/ai/flow_engine.py:1460`
- `huf/ai/document_artifact_instructions.py:53`
- `huf/ai/providers/elevenlabs_convai_api.py:132`
- `huf/ai/providers/elevenlabs_convai_api.py:138`
- `huf/ai/orchestration/orchestrator.py:141`

The remaining sites originally flagged as "ambiguous" by the automated pass
were re-checked by hand and confirmed **already safe** (no change needed):
`huf/ai/gateway_service.py:277` and `:524` (title is a static string, or the
dynamic value is `frappe.get_traceback()` which always contains a newline and
is protected by Frappe's own swap heuristic), `huf/ai/gateways/slack_events.py:17,22,44`
(title is already first, dynamic message is already second — correct order),
and `huf/ai/skills/importer.py:537` (first argument is a static translated
string well under 140 chars).

## Verification

- `python3 -m py_compile` on all 46 touched files: **passed**, no syntax
  errors.
- Provisioned a disposable bench (`fix-log-error-verify`, workspace `huf`,
  branch `fix/log-error-arg-order-cleanup`, blank site) via the
  `frappe-multihand` skill, on the `frappe_docker_devcontainer-frappe-1`
  devcontainer.
- Ran the full backend suite: `bench --site fix-log-error-verify.local
  run-tests --app huf`.
  - **Result: `Ran 1708 tests in 21.034s` — `OK (skipped=167)`.**
  - Zero failures, zero errors. No new failures were introduced by this
    change (there were none to compare against — the run against this branch
    was already fully clean).
- Bench left running for manual inspection (not torn down automatically —
  per policy, ask before tearing down a bench used for verification).
