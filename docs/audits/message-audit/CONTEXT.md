# CONTEXT — MessageAudit

| Field | Value |
|-------|-------|
| Track | `MessageAudit` |
| Huf piece | `product` ([`huf/`](../../huf/)) |
| Status | Done (Audit complete: STATE.md (as-built semantics), FINDINGS.md (MA-01..25), PLAN.md (4 phases); implementation phases queued as future tracks) |
| Last updated | 2026-07-18 |

## What
Audit of the **Agent Message** doctype and its context semantics — `context_policy`,
`record_kind`, `token_estimate`, `visibility`, `context_summary` (plus the `kind`/
`record_kind` duality and tool-call fields) — how they are written, read, and whether
the logic is sound. Extends to the structural observation that Huf keeps three
partially separate execution records (Agent Run, Agent Orchestration, Flow Run) while
Agent Message duplicates tool-call data already in Agent Tool Call.

## Goal
A documented, file:line-cited register covering: (1) current state of Agent Message
context fields (writers, readers, semantics); (2) soundness assessment of the
context-policy machinery; (3) the Agent Message ↔ Agent Tool Call duplication map;
(4) the three-execution-records overlap analysis; (5) gaps/locks/traps/issues
register; (6) an incremental unification plan. Docs-only — no product code changes.

## Source & working copy
- Reference (read-only): [`huf/`](../../huf/) symlink → `/Users/safwan/Code/Huf/huf`
- **Branch audited:** `feature/inline-video-playback` @ `eebb9dc` (same base as
  CodeDiscovery/CommitAudit; verified current for these semantics — `origin/develop`
  @ `95daa90` only fixes the `Queues` typo + adds Agent Run trigger refs, and
  `origin/feature/queue-first-agent-runs` @ `726762f` touches run lifecycle, not
  message context semantics).
- No working copy: docs-only track.
- Path note: repo nests the app one level deep — doctypes live at
  `huf/huf/huf/doctype/<name>/` from the workspace root; `huf/ai/` citations from
  CodeDiscovery resolve to `huf/huf/ai/`.

## Key files
- [`STATE.md`](STATE.md) — current-state report: schema, writers, readers, semantics per field.
- [`FINDINGS.md`](FINDINGS.md) — gaps/locks/traps/issues register (MA-xx IDs).
- [`PLAN.md`](PLAN.md) — incremental unification plan (phases, tasks).
- Upstream inputs: [`Tracks/CodeDiscovery/`](../CodeDiscovery/) (GLOSSARY, FINDINGS,
  ADR 0001/0002, discovery/02), [`Tracks/CommitAudit/`](../CommitAudit/) (REPORT).

## How to resume
1. Read this file, then `STATE.md` → `FINDINGS.md` → `PLAN.md`.
2. Code citations are repo-relative paths at `eebb9dc`; use the `huf/` symlink.
3. Cross-check terminology against `Tracks/CodeDiscovery/GLOSSARY.md` (frozen).
4. If implementing fixes: create a worktree inside this track, base on `develop`,
   and file issues on `tridz-dev/huf` (precedent: CodeDiscovery issues #363–#385).

## Constraints / gotchas
- Docs-only: do not edit code through the symlinked `huf/`.
- Queue-first (PR #362) is treated-as-merged per owner (CodeDiscovery F-03) but is
  **not** in the audited base; where behavior differs, it is flagged in STATE.md.
- `frappe.db.commit()` policy for message paths is CommitAudit's scope — referenced,
  not re-audited here.

## Verification pass (2026-07-18)
Independent re-verification of STATE/FINDINGS/PLAN at `eebb9dc`, orchestrated per
sub-task: 4 parallel kimi executors (policy table & history assembly; dead
fields/write census/public API; ATC duplication/merge/stream usage; execution
records & tests), each report reviewed and the load-bearing claims re-checked
first-hand by the orchestrator. Outcome: 23/25 findings confirmed as written;
**MA-14 withdrawn** (precedence claim was wrong — agent messages always get
`user="Agent"`); MA-11/MA-15 sharpened (3 MAX+1 copies in sdk_tools; stream-path
repair runs once per run, Error Log only on actual repairs); minor cite fixes
(chatApi path is `frontend/src/services/`, ChatMessage kind branches at :149/:169,
elevenlabs path under `providers/`, sync fallback lacks the 500-char floor).
