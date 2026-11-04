# CONTEXT — MessageAudit

| Field | Value |
|-------|-------|
| Track | `MessageAudit` |
| Huf piece | `product` ([`huf/`](../../huf/)) |
| Status | Rebased audit against current `origin/develop`; docs-only update. |
| Last updated | 2026-08-02 |

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
- Working copy: `/Users/safwan/Code/Huf/worktrees/artifact-result-context-v1` (branch
  `feat/artifact-result-context-v1`, rebased onto `origin/develop` @
  `2c3fd73c81d2af40a392c7dbd1976f6068019d20`).
- **Branch audited:** `origin/develop` @ `2c3fd73c81d2af40a392c7dbd1976f6068019d20`.
- `docs/audits/` does not exist on `origin/develop`; this audit is the docs-only PR
  #405 branch content.
- Path note: repo nests the app one level deep — doctypes live at
  `huf/huf/doctype/<name>/` from the workspace root; `huf/ai/` citations resolve to
  `huf/huf/ai/`.

## Key files
- [`STATE.md`](STATE.md) — current-state report: schema, writers, readers, semantics per field.
- [`FINDINGS.md`](FINDINGS.md) — gaps/locks/traps/issues register (MA-xx IDs).
- [`PLAN.md`](PLAN.md) — incremental unification plan (phases, tasks).
- Upstream inputs: [`Tracks/CodeDiscovery/`](../CodeDiscovery/) (GLOSSARY, FINDINGS,
  ADR 0001/0002, discovery/02), [`Tracks/CommitAudit/`](../CommitAudit/) (REPORT).

## How to resume
1. Read this file, then `STATE.md` → `FINDINGS.md` → `PLAN.md`.
2. Code citations are repo-relative paths at `origin/develop` @ `2c3fd73c`.
3. Cross-check terminology against `Tracks/CodeDiscovery/GLOSSARY.md` (frozen).
4. If implementing fixes: work in `/Users/safwan/Code/Huf/worktrees/artifact-result-context-v1`,
   base on `origin/develop` @ `2c3fd73c`, and file issues on `tridz-dev/huf`.

## Constraints / gotchas
- Docs-only: do not edit product code while updating this audit.
- `frappe.db.commit()` policy for message paths is CommitAudit's scope — referenced,
  not re-audited here.

## Relationship to Result Store and Artifact Workspace

- `Agent Message` is not the durable owner of large tool/API payloads.
- `Agent Tool Call` is not by itself a sufficient large-result store.
- Results require bounded envelopes and selective reads.
- Artifacts require immutable versions and operations.
- `Agent Context Artifact` is a compatibility/context bridge, not the canonical
  artifact registry.
- Result references and artifact references must be version-aware where mutation is
  possible.
- Message history must carry compact references, not complete work or unbounded
  results.

## Verification pass (2026-08-02)
Rebased audit against `origin/develop` @ `2c3fd73c`. Re-classified findings in
`FINDINGS.md` based on direct code checks; updated line numbers and census results in
`STATE.md`. Added the required relationship to Result Store and Artifact Workspace.
Track boundaries for `ResultContextFoundation` (Steps 1–3) and `Artifact Workspace V1`
(Step 4) are documented in `PLAN.md`.
