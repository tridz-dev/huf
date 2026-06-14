# Implementation Plans

This index tracks both the original security plans (PR #302) and the new round-2 plans.

## Original plans (PR #302, branch `doc/security-improvement-plans`)

| Plan | Title | Priority | Effort | Depends on | Status |
|------|-------|----------|--------|------------|--------|
| 001 | Characterization tests for `validate_url` & `safe_eval_expression` | P1 | M | — | TODO |
| 002 | Close SSRF bypass in `validate_url` (IPv6 + redirect re-validation) | P1 | M | 001 | TODO |
| 003 | Mandatory constant-time auth for `flow_webhook` | P2 | S | — | TODO |
| 004 | ElevenLabs webhook fail-closed + lock down guest endpoints | P1 | S | — | TODO |
| 005 | Require pinned `reference_doctype` for guest CRUD tools | P1 | M | — | TODO |
| 006 | Sandbox SVG artifacts to prevent stored XSS | P2 | S | — | TODO |
| 007 | Constrain `docs_renderer` paths to docs root | P3 | S | — | TODO |

## Round-2 plans (PR #303, branch `doc/security-improvement-plans-2`)

Full details are in `doc/security-improvement-plans-2.md`. This table is a quick index.

| Plan | Title | Priority | Effort | Depends on | Status |
|------|-------|----------|--------|------------|--------|
| 008 | Authorize conversation mutation APIs | P1 | M | — | TODO |
| 009 | Restrict `get_result_context` to allowed DocTypes and permissions | P1 | S | — | TODO |
| 010 | Add capability checks to Huf Data Table management APIs | P1 | S | — | TODO |
| 011 | Enforce file permission checks in `transcribe_audio` | P2 | S | — | TODO |
| 012 | Remove TTS/STT API key leakage via `os.environ` | P2 | S | — | TODO |
| 013 | Add per-document permission check in `delete_documents` | P2 | S | — | TODO |
| 014 | Harden HTML/SVG artifact rendering | P1 | S/M | — | TODO |
| 015 | Sandbox JSX previews to prevent arbitrary JS execution | P1 | M | — | TODO |
| 016 | Harden code-block rendering against XSS fallback | P1 | S | — | TODO |
| 017 | Replace HTML-parser entity decoder with pure string replacement | P2 | S | — | TODO |
| 018 | Validate `returnTo` navigation from `localStorage` | P2 | S | — | TODO |
| 019 | Upgrade vulnerable frontend lockfile dependencies | P1 | S/M | — | TODO |
| 020 | Upgrade vulnerable Python dependencies | P1 | M | — | TODO |
| 021 | Remove hardcoded development credentials | P3 | S | — | TODO |

## Dependency notes

- Plan 008 is a prerequisite for any future chat/conversation data features.
- Plans 014/015/016/017/018 are independent frontend hardening items.
- Plans 019 and 020 should land before risky code changes so CI catches new advisories early.

## Status values

TODO | IN PROGRESS | DONE | BLOCKED (with reason) | REJECTED (with rationale)
