# Hub Simple Fixes — 05

**Branch:** `feat/design-simplified-hub-homepage-interface`  
**HEAD:** `4a28794d4968ce5284be3459906eb66aa4f16140`  
**Commit:** `feat(agent): add is_system protection; fix hub role detection`

---

## T1 — `is_system` field on Agent

### Changed files

1. `huf/huf/doctype/agent/agent.json`
   - Added `is_system` to `field_order` after `source_file` (line 106).
   - Added field definition (lines 705–712):
     - `fieldtype`: `Check`
     - `default`: `0`
     - `hidden`: `1`
     - `read_only`: `1`
     - Placed immediately after the `source_file` provenance field.
   - Bumped `modified` timestamp to `2026-07-17 13:11:19.673477`.

2. `huf/huf/doctype/agent/agent.py`
   - `validate()` now calls `_validate_system_field_tamper()` (line 113).
   - New `_validate_system_field_tamper()` (lines 125–144):
     - Skips new documents.
     - Skips if `is_system` did not change.
     - Allows the change only when `frappe.flags.in_seeding`, `in_install`, `in_migrate` is set, or the current user is a System Manager.
     - Otherwise throws `frappe.ValidationError`.
   - `on_trash()` (lines 308–313) now blocks deletion of `is_system` agents unless `frappe.flags.in_install/in_migrate/in_uninstall` is set.
   - New `before_rename()` (lines 315–319) blocks rename of `is_system` agents unless the same install/migrate/uninstall flags are set.

3. `huf/ai/app_seeding/loaders.py`
   - `upsert_agent()` (line 131) documents that `is_system` is a pass-through field preserved by `_upsert_doc` via `doc.update()`.

4. `huf/ai/app_seeding/seeder.py`
   - `seed_app()` sets `frappe.flags.in_seeding = True` before the load loop and resets it in a `finally` block (lines 36, 78–79).
   - This makes the tamper guard's seeding branch meaningful and keeps seed-driven agent updates explicit.

### Notes / uncertainty
- The install/migrate/uninstall exemptions for delete/rename are defensive: they prevent users from breaking seeded system agents while still allowing infrastructure operations to clean up if necessary.
- `disabled=1` is intentionally **not** blocked; admins may need to disable a system agent without deleting it.

---

## T2 — Fix Hub role detection

### Changed files

1. `frontend/src/pages/HubSimplePage.tsx`
   - Replaced `const { capabilities } = usePermissions()` with `const { hufRole } = usePermissions()` (line 62).
   - Replaced the broken `capabilities.includes('system.admin')` derivation with a mapping against the real `huf_role` returned by `get_me` (lines 64–68):
     - `Huf Admin` → `admin`
     - `Huf Manager` / `Huf User` → `builder`
     - everything else (`Huf Viewer`, no role) → `viewer`
   - Removed the dead `operator` entry from `GREETINGS` (line 26).
   - Removed the dead `operator` starter-prompt branch (lines 42–48).

### Notes / uncertainty
- `PermissionsContext` already exposed `hufRole` (mapped from `get_me.huf_role`), so no context/service changes were required.
- `System Manager` users are mapped to `Huf Admin` on the backend (`get_user_huf_role`), so they resolve to `admin` here without an extra client-side check.

---

## T3 — Tests / gates

### Backend tests
- Updated `huf/huf/doctype/agent/test_agent.py` with three minimal tests:
  - `test_system_agent_delete_guard` (lines 9–15)
  - `test_system_agent_rename_guard` (lines 17–23)
  - `test_system_agent_tamper_guard` (lines 25–41)
- **Not run:** no Frappe site/bench directory is available in this working copy (`bench` exists but the repo is the app, not a bench). The tests were written following the existing `FrappeTestCase` pattern.

### Frontend gates
- `cd frontend && yarn typecheck` — **PASS** (`tsc --noEmit -p tsconfig.app.json`, no errors).
- `cd frontend && yarn lint` — **FAIL**, but failures are **pre-existing** across the codebase (`any` types, unused variables, hook dependency warnings, etc.). `eslint src/pages/HubSimplePage.tsx` ran clean, so this change introduced no new lint errors.
- `git grep "system.admin" frontend/src` — **no matches** (exit code 1, i.e. no results).

### Python lint
- `ruff check` on the touched Python files reports many **pre-existing** issues (import ordering, trailing whitespace, `List` → `list`, etc.). The newly added code does not introduce new ruff diagnostics.

---

## Verdict

- Backend implementation: complete, tests written but not executed due to missing site.
- Frontend implementation: complete, typecheck clean, no new lint errors, dead `system.admin` reference removed.
- Overall: **CLEAN** with the caveat that backend tests and full `yarn lint` (because of unrelated pre-existing failures) could not be validated end-to-end.
