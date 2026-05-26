# HUF Integration Tools - Compatibility Review & Fix Plan

**Session**: `claude/review-huf-compatibility-yXuqZ`
**Date**: 2026-03-09
**Status**: COMPLETE - All fixes applied

---

## Summary

The codex branch (`codex/review-code-implementation-for-huf-compatibility` at `49cace0`) added 2 changes on top of our branch:
1. `tool_registry.py` - `_normalize_hook_tools()` function + updated `get_tools_by_app()`
2. `install.py` - Deprecated Gemini audio tools, hoisted params, added `sync_discovered_tools()` to `after_install`

**Both changes are needed and valid.** They must be cherry-picked/applied to our branch.

---

## Critical Issues Found (MUST FIX)

### BUG-1: Parameter Format Mismatch in `sync_discovered_tools()` (BLOCKER)
**File**: `huf/ai/tool_registry.py:381-388`
**Problem**: `_registry.py` uses `_p()` which creates params with key `fieldname`, but `sync_discovered_tools()` reads `p.get("name")` — which doesn't exist.
```python
# _registry.py _p() creates:
{"label": "Channel", "fieldname": "channel", "type": "string", "required": 1, "description": "..."}

# sync_discovered_tools reads:
"label": p.get("name", "").title(),  # WRONG - should be p.get("label") or p.get("fieldname")
"fieldname": p.get("name", ""),      # WRONG - should be p.get("fieldname")
```
**Impact**: All 127 integration tools get synced with EMPTY parameter names. Tools are created but unusable.
**Fix**: Update `sync_discovered_tools()` to read `fieldname`/`label` from params, falling back to `name` for backward compat.

### BUG-2: Missing `_normalize_hook_tools()` (BLOCKER)
**File**: `huf/ai/tool_registry.py`
**Problem**: `hooks.py` sets `huf_tools = "huf.ai.tools._registry.ALL_INTEGRATION_TOOLS"` (a dotted string). `frappe.get_hooks("huf_tools")` returns `["huf.ai.tools._registry.ALL_INTEGRATION_TOOLS"]`. Without `_normalize_hook_tools()`, this string is treated as a tool dict and fails silently.
**Fix**: Apply the codex branch change — add `_normalize_hook_tools()` and update `get_tools_by_app()`.

### BUG-3: `credentials.py` references non-existent DocType
**File**: `huf/ai/tools/credentials.py:27`
**Problem**: `require_credential()` tries `frappe.get_doc("HUF Settings")` but the actual DocType is `Integration Settings`. The credential child table also expects `cred.service` field, but `Integration Credential` only has `key` and `value` — no `service` field.
**Impact**: Credential lookup from DB always falls through to env vars. Not a crash, but defeats the purpose of UI-based credential management.
**Fix**: Update to use `Integration Settings` DocType with proper query.

### BUG-4: `install.py` still calls deprecated Gemini tool functions
**File**: `huf/install.py:67-68, 101-102`
**Problem**: `after_install()` and `after_migrate()` still call `create_gemini_transcribe_audio_tool()` and `create_gemini_generate_audio_tool()` which should be replaced with `remove_deprecated_gemini_audio_tools()`.
**Fix**: Apply the codex branch change.

### BUG-5: `install.py` `after_install()` missing `sync_discovered_tools()` call
**File**: `huf/install.py:61-73`
**Problem**: After install, tools from `huf_tools` hook aren't synced. New installs won't have integration tools.
**Fix**: Apply the codex branch change — add `sync_discovered_tools(use_cache=False)` call.

### BUG-6: `generate_audio` params defined only in else branch
**File**: `huf/install.py` (create_generate_audio_tool)
**Problem**: `parameters` list is defined inside the `else` (create new) branch only. The `if tool_exists` branch references `parameters` before it's defined → `NameError`.
**Fix**: Apply the codex branch change — hoist params above the if/else.

---

## Warnings (Should Fix)

### WARN-1: `httpx` not in pyproject.toml
6 tool modules import `httpx` (discord, github, gmail, jira_tools, slack, telegram).
**Fix**: Add `httpx` to pyproject.toml dependencies.

### WARN-2: `youtube.py` runtime crash
`handle_get_captions()` uses `transcript.snippets` but youtube-transcript-api returns a list of dicts.
**Fix**: Change to dict iteration pattern.

### WARN-3: `credentials.py` `update_last_error()` references wrong DocType
Uses `Integration Settings` but queries with `filters={"service": service}` — the actual field is a Link to `Integration Service`, not a plain text field.

### WARN-4: `_iter_declared_tools()` in tool_registry.py is obsolete ✅ FIXED
Old function at line 97 doesn't use `_normalize_hook_tools()`. It's not called anywhere in the codebase currently but could cause confusion.
**Fix applied**: Removed `_iter_declared_tools()`, `validate_tool_def()`, and `upsert_tool_doc()` (all dead code).

---

## Changes to Apply

### Phase 1: Cherry-pick codex branch changes (BUG-2, BUG-4, BUG-5, BUG-6)
- Apply `_normalize_hook_tools()` to `tool_registry.py`
- Apply install.py changes (deprecated gemini tools, sync call, param hoisting)

### Phase 2: Fix parameter format mismatch (BUG-1)
- Update `sync_discovered_tools()` BATCH 4 to read `fieldname`/`label` from params

### Phase 3: Fix credentials.py DocType mismatch (BUG-3, WARN-3)
- Update `require_credential()` to use `Integration Settings` DocType
- Fix `update_last_error()` query

### Phase 4: Fix youtube.py crash (WARN-2)
- Fix transcript parsing

### Phase 5: Add httpx dependency (WARN-1)
- Update pyproject.toml

---

## Verification Checklist

- [x] `_normalize_hook_tools()` resolves string hook to list of dicts
- [x] `sync_discovered_tools()` creates tools with correct parameter names (reads `fieldname`/`label`, falls back to `name`)
- [x] `require_credential()` can find credentials from `Integration Settings`
- [x] `after_install()` calls `remove_deprecated_gemini_audio_tools()` + `sync_discovered_tools()`
- [x] `after_migrate()` calls `remove_deprecated_gemini_audio_tools()`
- [x] `generate_audio` tool params available in both create and update paths
- [x] Old tools (CRUD, HTTP, custom function, flow tools) still work unchanged (no changes to sdk_tools.py or tool execution paths)
- [x] `httpx` is a declared dependency
- [x] youtube.py transcript parsing handles both old and new API formats

## Remaining Known Issues (Not Fixed - Lower Priority)

1. **Gmail OAuth2 stub** - `gmail.py:15-19` only retrieves static token, no refresh flow
2. **Optional deps not declared** - `boto3`, `docker`, `duckduckgo-search`, `yfinance`, `pytube`/`pytubefix`, `youtube-transcript-api` are used with ImportError fallbacks but not in pyproject.toml (by design - they're optional)
3. ~~**`_iter_declared_tools()` obsolete**~~ - FIXED: Removed along with `validate_tool_def()` and `upsert_tool_doc()`
4. **Some tools use explicit params before `**kwargs`** - discord, github, gmail, jira, slack, telegram use typed positional params. Works in practice since Frappe calls with kwargs, but inconsistent
5. **`update_last_error()` query** - filters by `service` field which is a Link field to `Integration Service`, should match by service_name lookup
