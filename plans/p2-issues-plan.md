# Scoped Memory — P2 Issues Plan

**Branch:** `feature/scoped-memory-implementation` (PR #282)
**Status:** P0/P1 remediation complete. This file catalogs P2 (lower-severity quality/correctness) issues.

---

## P2 Issue List

### P2-1 — `policy.enabled` flag never checked (silent dead config)
**Where:** `huf/ai/agent_integration.py:281`, `huf/ai/memory_tools.py`  
**Why:** `MemoryPolicy` has an `enabled` Check field (default=1). Neither the injection path (`get_injected_memory_text`) nor the extraction path (`run_background_memory_extraction`) checks `policy.enabled` before proceeding. A policy set to `enabled=0` is still fully active.  
**Fix:** Check `policy.enabled` early in both paths and bail out if `not policy.enabled`.

---

### P2-2 — `self._conversation_id` never set on `AgentManager` (injection always gets `None`)
**Where:** `huf/ai/agent_integration.py:287`  
**Why:** P1-8 fix passes `conversation_id=getattr(self, '_conversation_id', None)` to `get_injected_memory_text`. But `AgentManager` has no `_conversation_id` attribute — it's set at invocation time (in `run_agent_sync`/streaming path), not on the manager. So injection always gets `None` → Conversation-scoped memories never inject.  
**Fix:** Accept `conversation_id` as a parameter to `create_agent()`, or pass it through `get_injected_memory_text` at the call-site in the run path instead of on `create_agent`.

---

### P2-3 — Memory injection ignores `policy.enabled` + `Tool Only` inject_mode
**Where:** `huf/ai/memory_tools.py:get_injected_memory_text`  
**Why:** The function handles `"Never"` but treats `"Tool Only"` as "inject automatically" (since it falls through to the injection logic). `"Tool Only"` should mean: the agent can use the tool to search, but nothing is auto-injected into the system prompt. Currently there's no difference between `"Always"` and `"Tool Only"` at injection time.  
**Fix:** Add `"Tool Only"` to the list of inject_modes that return `None` from `get_injected_memory_text`.

---

### P2-4 — Knowledge projection calls use `ignore_permissions=False` in background context
**Where:** `huf/huf/doctype/memory_record/memory_record.py:121,125`  
**Why:** `project_memory_to_knowledge` is a background-queued function. When running as a queued job, `frappe.session.user` is `Administrator` and permissions generally work. BUT if a non-manager Memory Record owner triggers projection via P0-5's `auto_promote_to_knowledge` path, the background job saves the Knowledge Input with `ignore_permissions=False`. This can fail if `Knowledge Input` perms are also restricted. Since projection is manager-only per `promote_memory_to_knowledge`'s `_is_manager()` guard, using `ignore_permissions=True` here is safe and consistent.  
**Fix:** Change Knowledge Input `insert/save` in `project_memory_to_knowledge` to `ignore_permissions=True`.

---

### P2-5 — `run_background_memory_extraction` uses `frappe.session.user` as fallback owner
**Where:** `huf/ai/agent_integration.py:683`  
**Why:** `scope_key=frappe.db.get_value("Agent Conversation", conversation_name, "owner") or frappe.session.user` — in a background job, `frappe.session.user` is `Administrator`, so if the conversation has no `owner` (shouldn't happen but possible with legacy data), memories are scoped to Administrator instead of raising an error.  
**Fix:** Raise or skip gracefully if `conv_owner` is blank rather than silently scoping to Administrator.

---

### P2-6 — `memory_record.json` `source_type` field missing from `fields` displayed in list/form
**Where:** `huf/huf/doctype/memory_record/memory_record.json`  
**Why:** `source_type` is not in `in_list_view` or the standard view fields that include the new `Extracted` value. This is minor UI polish — `Extracted` records show correctly in the form but aren't visible in list view filtering.  
**Fix:** Set `in_list_view: 1` on `source_type` field so it appears in list columns. (Or confirm it's already there.)

---

### P2-7 — `memory_tools.py` uses 4-space indentation (project style is tabs)
**Where:** No — I used tabs throughout `memory_tools.py`. But let me double-check the controller files.  
**Status:** Already verified as tab-indented. No fix needed.

---

### P2-8 — `memory_record.py` and `memory_policy.py` use 4-space indentation (project mixes)
**Where:** `huf/huf/doctype/memory_record/memory_record.py`, `huf/huf/doctype/memory_policy/memory_policy.py`  
**Why:** These new files from the feature branch use 4-space indentation. The project's ruff config expects tabs (110 col). The audit plan §context explicitly warns about this.  
**Fix:** Convert both controller files from 4-spaces to tabs.

---

### P2-9 — `remove_memory_knowledge_projection` uses `ignore_permissions=False` on `frappe.delete_doc`
**Where:** `huf/huf/doctype/memory_record/memory_record.py:81`  
**Why:** Same inconsistency as P2-4 — the handler is only reachable by managers (per `promote_memory_to_knowledge` guard), but the delete uses `ignore_permissions=False`. Using `ignore_permissions=True` is safe and consistent.  
**Fix:** Change to `ignore_permissions=True`.

---

### P2-10 — Daily scheduler hook for expiry not wired up
**Where:** `huf/hooks.py`  
**Why:** P1-7 added read-time expiry filtering (defense in depth), and the audit plan noted an *optional* daily scheduler to flip `status="Expired"` proactively. This is missing. Without it, expired records remain `Active` in the DB forever, accumulating stale data.  
**Fix:** Add `huf.ai.memory_tools.expire_stale_memory_records` to `hooks.py` daily scheduler, and implement the function.

---

## Execution Order

1. P2-3 (Tool Only inject mode) — fixes `get_injected_memory_text`, no deps
2. P2-1 (policy.enabled check) — add enabled gate in injection + extraction
3. P2-2 (_conversation_id never set) — pass conversation_id properly at run-time
4. P2-4 + P2-9 (ignore_permissions in projection) — trivial, do together
5. P2-5 (fallback owner) — safety guard in extraction
6. P2-8 (indentation) — convert controllers to tabs
7. P2-10 (expiry scheduler) — add daily hook + function
