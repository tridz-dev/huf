# Scoped Memory P0/P1 Fixes — TODO

> Local tracking file. NOT committed. NOT pushed to PR.
> Branch: `feature/scoped-memory-implementation` (PR #282)

## Progress Legend
- [ ] Not started
- [~] In progress  
- [x] Done

---

## Batch A — P0-1 (Blocker)

- [x] **P0-1**: Resolve merge conflict in `install.py` → commit ✓ (fbda938)

---

## Batch B — Backends

- [x] **P0-6**: Fix SQL parameter ordering in `sqlite_fts.py` and `sqlite_hybrid.py` ✓ (786ffeb)
- [x] **P1-1**: Add metadata filter key allowlist (SQL injection guard) in all 3 backends ✓ (786ffeb)
- [x] **P1-2**: Add `sqlite_hybrid` to `knowledge_source.json` `knowledge_type` options + depends_on ✓ (786ffeb)
- [x] **P1-3**: Rewrite `FULL OUTER JOIN` as `LEFT JOIN + UNION` in `sqlite_hybrid.py` ✓ (786ffeb)

---

## Batch C — Permissions

- [x] **P0-5**: Model A chosen — `ignore_permissions=True` in handlers, `_can_*` as sole authority ✓ (30261ef)
- [x] **P0-4**: Re-derive auth context via `_owns_conversation()`, stop trusting caller-supplied params ✓ (30261ef)
- [x] **P0-7**: Delete inline memory closures; use sdk_tools path instead ✓ (30261ef)
- [x] **P1-5**: Remove `@frappe.whitelist()` from `run_background_memory_extraction` ✓ (30261ef)
- [x] **P1-8**: Harden memory injection (pass conversation_id + XML envelope) ✓ (30261ef)

---

## Batch D — Extraction

- [x] **P0-3**: Add `Extracted` to `source_type` options in `memory_record.json` ✓ (30261ef)
- [x] **P0-2**: Fix `UnboundLocalError` (delete local `import json` in extraction fn) ✓ (30261ef)
- [x] **P1-6**: Deduplicate background extraction (job_id dedup + existing-facts prompt) ✓ (30261ef)

---

## Batch E — Independent

- [x] **P1-4**: Enforce Memory Policy write switches in `_can_write_memory` ✓ (30261ef)
- [x] **P1-7**: Filter expired memories at read time in search + injection ✓ (30261ef)
- [x] **P1-9**: Frontend fields — decision: desk-only for v1, noted in PR description ✓ (PR updated)

---

## Notes / Decisions Made
- Model A selected for P0-5 (custom `_can_*` as sole authority, `ignore_permissions=True`)
- P1-9: desk-only for v1 — noted in PR #282 description
- P0-7: deleted inline closures, sdk_tools path is now the only path

---

## Commits Made
- `fbda938` — fix: resolve merge conflict in after_migrate (P0-1)
- `786ffeb` — fix: harden knowledge backends (P0-6, P1-1, P1-2, P1-3)
- `30261ef` — fix: harden scoped memory security and correctness (P0-2, P0-3, P0-4, P0-5, P0-7, P1-4, P1-5, P1-6, P1-7, P1-8)

All commits pushed to `origin/feature/scoped-memory-implementation`.
PR #282 description updated with full audit remediation notes.

## STATUS: ✅ COMPLETE
