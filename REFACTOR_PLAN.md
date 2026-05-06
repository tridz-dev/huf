# Refactor Plan: `huf/ai/sdk_tools.py` and Related Modules

## Executive Summary

`sdk_tools.py` is the largest file in the backend at **2,682 lines / 96KB**. It has grown into a "god module" that handles tool creation, CRUD handlers, image generation, OCR, TTS, STT, conversation data management, and model resolution -- all in a single file with no clear boundaries. This plan breaks it into focused, testable modules following Python and Frappe best practices.

---

## Current Problems

### 1. Single Responsibility Violation (Critical)
`sdk_tools.py` contains **7 distinct responsibilities**:
- Tool creation and SDK integration (lines 1-365)
- Document CRUD handlers (lines 453-996)
- Conversation data handlers (lines 1113-1229)
- Image generation (lines 1231-1516)
- OCR/document processing (lines 1518-1892)
- Text-to-speech (lines 1893-2413)
- Speech-to-text / transcription (lines 2415-2683)

### 2. Duplicated Tool-Type-to-Handler Mapping
The `if/elif` chain mapping tool types to handler paths (lines 88-130) is **duplicated verbatim** in `flow_tool_executor.py` (lines 121-143). Any new tool type must be updated in both places -- a guaranteed source of bugs.

### 3. Duplicate Imports and Dead Code
- `base64` imported twice (lines 5 and 11)
- `save_file` imported twice (lines 6 and 12)
- `inspect` imported at module level (line 1) *and* inside `on_invoke_tool` (line 314)
- `datetime` imported at module level (line 24) *and* inline in `handle_create_document` (line 687) and `handle_get_list` (line 830)
- `create_*_function`, `create_list_function` factory functions (lines 480-647) appear unused -- `create_agent_tools()` routes through `handle_*` functions instead

### 4. Inconsistent Indentation
Mix of tabs and spaces throughout the file. Some functions use tabs (e.g., `get_function_from_name` at line 367), others use spaces (e.g., `handle_create_document` at line 652). Violates the project's ruff config.

### 5. Massive Copy-Paste Patterns in Media Handlers
Image generation, audio generation, and OCR all repeat the same boilerplate:
- Get agent doc and provider doc (~10 lines each)
- Get conversation_index via raw SQL (~8 lines each, repeated **4 times**)
- Create Agent Message doc (~15 lines each, repeated **4 times**)
- Save file and get URL (~10 lines each, repeated **3 times**)
- Emit socket event (~15 lines each, repeated **4 times**)
- Update conversation total_messages via raw SQL (~6 lines each, repeated **4 times**)

This is ~200+ lines of near-identical code that should be shared helpers.

### 6. `conversation_data_tools.py` is Partially Redundant
The file contains its own copies of `_now_iso_utc()` and `_load_state()` that are also in `sdk_tools.py` (lines 1114-1136). The handlers in `conversation_data_tools.py` duplicate those in `sdk_tools.py`.

### 7. `tool_functions.py` Has a Duplicate Function Definition
`attach_file_to_document()` is defined **twice** (lines 359 and 461). The first definition is dead code since Python silently overwrites it.

### 8. Filename Typo
`cilent_side_tool.py` should be `client_side_tool.py`.

### 9. No `__init__.py` for the `ai` Package
The `huf/ai/` directory has no `__init__.py`, making it not a proper Python package. The sub-packages (`knowledge/`, `providers/`, `orchestration/`) have `__init__.py` files.

---

## Proposed Module Structure

```
huf/ai/
├── __init__.py                      # NEW - package init
├── sdk_tools.py                     # SLIMMED - only tool creation + SDK wiring (~250 lines)
├── tool_registry.py                 # EXISTING - tool discovery (no changes)
├── tool_serializer.py               # EXISTING - tool format conversion (no changes)
├── tool_functions.py                # EXISTING - cleanup duplicate, keep CRUD primitives
├── tool_types.py                    # NEW - single source of truth for tool-type-to-handler mapping
├── handlers/                        # NEW - directory for tool handler functions
│   ├── __init__.py
│   ├── crud.py                      # EXTRACTED from sdk_tools.py - document CRUD handlers
│   ├── conversation_data.py         # EXTRACTED from sdk_tools.py - conversation data handlers
│   ├── media.py                     # EXTRACTED from sdk_tools.py - image gen, TTS, STT, OCR
│   └── agent_runner.py              # EXTRACTED from sdk_tools.py - handle_run_agent
├── media_utils.py                   # NEW - shared helpers for media handlers
├── http_handler.py                  # EXISTING - minor fixes
├── client_side_tool.py              # RENAMED from cilent_side_tool.py
├── agent_integration.py             # EXISTING - minor import updates
├── flow_tool_executor.py            # EXISTING - use tool_types.py instead of hardcoded map
├── ...                              # remaining files unchanged
```

---

## Detailed Changes

### Phase 1: Foundation (Low Risk)

#### 1.1 Create `huf/ai/__init__.py`

Create an empty `__init__.py` to make `huf/ai/` a proper Python package.

```python
# huf/ai/__init__.py
```

**Reasoning**: Every Python package should have an `__init__.py`. Without it, some import patterns may behave unexpectedly, and tools like pytest may not discover tests correctly.

---

#### 1.2 Create `huf/ai/tool_types.py` -- Single Source of Truth for Tool Type Mapping

Extract the tool-type-to-handler-path mapping that is currently duplicated between `sdk_tools.py` (lines 88-130) and `flow_tool_executor.py` (lines 121-143) into a single constant.

```python
# huf/ai/tool_types.py
"""
Single source of truth for mapping tool types to their handler function paths.

Used by both sdk_tools.create_agent_tools() and flow_tool_executor.execute().
"""

TOOL_TYPE_HANDLERS: dict[str, str] = {
	"Get List": "huf.ai.handlers.crud.handle_get_list",
	"Get Document": "huf.ai.handlers.crud.handle_get_document",
	"Update Document": "huf.ai.handlers.crud.handle_update_document",
	"Create Document": "huf.ai.handlers.crud.handle_create_document",
	"Delete Document": "huf.ai.handlers.crud.handle_delete_document",
	"Get Multiple Documents": "huf.ai.handlers.crud.handle_get_documents",
	"Create Multiple Documents": "huf.ai.handlers.crud.handle_create_documents",
	"Update Multiple Documents": "huf.ai.handlers.crud.handle_update_documents",
	"Delete Multiple Documents": "huf.ai.handlers.crud.handle_delete_documents",
	"Submit Document": "huf.ai.handlers.crud.handle_submit_document",
	"Cancel Document": "huf.ai.handlers.crud.handle_cancel_document",
	"Get Value": "huf.ai.handlers.crud.handle_get_value",
	"Set Value": "huf.ai.handlers.crud.handle_set_value",
	"Get Report Result": "huf.ai.handlers.crud.handle_get_report_result",
	"GET": "huf.ai.http_handler.handle_get_request",
	"POST": "huf.ai.http_handler.handle_post_request",
	"Run Agent": "huf.ai.handlers.agent_runner.handle_run_agent",
	"Attach File to Document": "huf.ai.handlers.crud.handle_attach_file_to_document",
	"Get Conversation Data": "huf.ai.handlers.conversation_data.handle_get_conversation_data",
	"Set Conversation Data": "huf.ai.handlers.conversation_data.handle_set_conversation_data",
	"Load Conversation Data": "huf.ai.handlers.conversation_data.handle_load_conversation_data",
}

# Tool types that require a reference_doctype extra_arg
DOCTYPE_BOUND_TYPES: frozenset[str] = frozenset({
	"Get Document", "Get Multiple Documents", "Get List",
	"Create Document", "Create Multiple Documents",
	"Update Document", "Update Multiple Documents",
	"Delete Document", "Delete Multiple Documents",
	"Attach File to Document",
})
```

**Reasoning**: The DRY principle. Both `sdk_tools.py` and `flow_tool_executor.py` currently maintain identical mappings. Adding a new tool type today requires remembering to update both files. With a shared constant, it's one change in one place.

**References to update**:
- `sdk_tools.py` lines 88-130 → use `TOOL_TYPE_HANDLERS.get(function_doc.types)`
- `flow_tool_executor.py` lines 121-143 → use `from huf.ai.tool_types import TOOL_TYPE_HANDLERS`
- `flow_tool_executor.py` lines 148-173 → use `DOCTYPE_BOUND_TYPES`

---

#### 1.3 Rename `cilent_side_tool.py` → `client_side_tool.py`

Fix the typo in the filename. Update the single reference in `sdk_tools.py` line 84:

```python
# Before
function_path = "huf.ai.cilent_side_tool.client_side_function"

# After
function_path = "huf.ai.client_side_tool.client_side_function"
```

**References to update**:
- `sdk_tools.py` line 84
- Any `install.py` references

---

### Phase 2: Extract Handler Modules (Medium Risk)

#### 2.1 Create `huf/ai/handlers/__init__.py`

Empty init file for the handlers sub-package.

---

#### 2.2 Extract `huf/ai/handlers/crud.py`

Move all document CRUD handlers out of `sdk_tools.py`:

| Function | Current Location (sdk_tools.py) | Notes |
|----------|-------------------------------|-------|
| `_sanitize_for_doctype()` | line 453 | Private helper, used by create/update |
| `handle_create_document()` | line 652 | |
| `handle_delete_document()` | line 698 | |
| `handle_get_list()` | line 736 | |
| `handle_update_document()` | line 854 | |
| `handle_get_document()` | line 899 | |
| `handle_create_documents()` | line 949 | Delegates to `tool_functions.create_documents` |
| `handle_update_documents()` | line 962 | Delegates to `tool_functions.update_documents` |
| `handle_delete_documents()` | line 978 | Delegates to `tool_functions.delete_documents` |
| `handle_submit_document()` | line 981 | |
| `handle_cancel_document()` | line 989 | |
| `handle_get_value()` | line 997 | |
| `handle_set_value()` | line 1022 | |
| `handle_get_report_result()` | line 1053 | |
| `handle_attach_file_to_document()` | line 1082 | |

**Also remove** the unused factory functions (lines 480-647):
- `create_get_function()`
- `create_create_function()`
- `create_update_function()`
- `create_delete_function()`
- `create_list_function()`
- `wrap_frappe_function()`

These are never called -- `create_agent_tools()` uses the `handle_*` pattern exclusively. If they were once used, that usage has been replaced. Confirm by grepping for callers before removing.

**Cleanup during extraction**:
- Remove duplicate `import datetime` statements (use module-level import)
- Standardize indentation to tabs (per ruff config)
- Remove inline `import base64` / `import datetime` -- put at module top

**Reasoning**: CRUD handlers are a self-contained concern. They don't need access to FunctionTool, asyncio, or media processing. Extracting them makes each file easier to read and test.

---

#### 2.3 Extract `huf/ai/handlers/conversation_data.py`

Move conversation data handlers out of `sdk_tools.py`. **Delete** the redundant `conversation_data_tools.py` file.

| Function | Current Location (sdk_tools.py) |
|----------|-------------------------------|
| `_now_iso_utc()` | line 1114 |
| `_load_state()` | line 1118 |
| `handle_get_conversation_data()` | line 1138 |
| `handle_set_conversation_data()` | line 1158 |
| `handle_load_conversation_data()` | line 1219 |

**References to update**:
- `tool_types.py` handler paths (already using new path)
- Delete `huf/ai/conversation_data_tools.py` (its functions are duplicates)

**Reasoning**: Conversation data is a distinct concern from document CRUD and media processing.

---

#### 2.4 Extract `huf/ai/handlers/agent_runner.py`

Move `handle_run_agent()` (sdk_tools.py line 1056) to its own file.

```python
# huf/ai/handlers/agent_runner.py
import frappe
from frappe.utils.background_jobs import enqueue


def handle_run_agent(agent_name: str, prompt: str, **kwargs):
	"""Queue another agent execution instead of blocking."""
	...
```

**Reasoning**: This handler has a unique dependency on `frappe.utils.background_jobs.enqueue` that no other handler needs. Keeping it separate prevents unnecessary coupling.

---

#### 2.5 Create `huf/ai/media_utils.py` -- Shared Media Handler Helpers

Extract the repeated boilerplate from image/audio/OCR handlers into reusable helpers:

```python
# huf/ai/media_utils.py
"""Shared utilities for media tool handlers (image, audio, OCR)."""

import frappe
from frappe.utils.file_manager import save_file


def get_agent_provider_config(agent_name: str) -> tuple:
	"""Load agent doc, provider doc, and decrypted API key.

	Returns:
		(agent_doc, provider_doc, api_key)

	Raises:
		ValueError if agent not found or API key missing.
	"""
	...


def get_next_conversation_index(conversation_id: str) -> int:
	"""Get the next sequential conversation_index for a conversation."""
	...


def create_agent_message(
	conversation_id: str,
	agent_name: str,
	agent_doc,
	kind: str,
	content: str,
	conversation_index: int,
	agent_run_id: str = None,
	**extra_fields,
) -> "frappe.Document | None":
	"""Create an Agent Message document. Returns None on failure (logs error)."""
	...


def save_media_file(
	filename: str,
	content: bytes,
	message_doc=None,
	conversation_id: str = None,
	field_name: str = None,
	is_private: bool = False,
) -> tuple[str, str]:
	"""Save a media file, attach to message or conversation.

	Returns:
		(file_url, file_id)
	"""
	...


def emit_message_event(
	conversation_id: str,
	message_doc,
	kind: str,
	extra_data: dict = None,
):
	"""Publish a realtime socket event for a new agent message."""
	...


def update_conversation_total_messages(conversation_id: str, index: int):
	"""Update the conversation's total_messages and last_activity."""
	...
```

**Reasoning**: These 6 operations are repeated 3-4 times across the media handlers with only minor variations. Extracting them eliminates ~200 lines of duplicated code and ensures consistent behavior (e.g., if the Agent Message schema changes, you update one place).

---

#### 2.6 Extract `huf/ai/handlers/media.py`

Move all media-related handlers to a single file, using `media_utils.py` helpers:

| Function | Current Location (sdk_tools.py) | Lines |
|----------|-------------------------------|-------|
| `_get_default_image_model()` | 1231 | |
| `handle_generate_image()` | 1256 | ~260 lines → ~80 with helpers |
| `_determine_ocr_strategy()` | 1518 | |
| `_get_default_ocr_model()` | 1535 | |
| `_process_with_ocr_endpoint()` | 1558 | |
| `_process_with_vision_model()` | 1628 | |
| `handle_ocr_document()` | 1690 | ~200 lines → ~60 with helpers |
| `_get_default_voice()` | 1893 | |
| `_get_default_tts_model()` | 1906 | |
| `_TTS_ENV_VAR_PROVIDERS` | 1931 | |
| `_resolve_tts_config()` | 1940 | |
| `_get_default_stt_model()` | 2071 | |
| `_resolve_stt_config()` | 2083 | |
| `handle_generate_audio()` | 2171 | ~240 lines → ~70 with helpers |
| `handle_transcribe_audio()` | 2416 | ~265 lines → ~80 with helpers |

**Estimated reduction**: From ~1,450 lines of media code to ~600 lines (handlers + helpers + utils).

**Reasoning**: All four media handlers share the same lifecycle: resolve model → call LiteLLM → save result → create message → emit event. Grouping them together and extracting shared steps makes the pattern obvious and maintainable.

---

### Phase 3: Slim Down `sdk_tools.py` (Low Risk After Phase 2)

After extraction, `sdk_tools.py` should contain only:

1. `_check_tool_permission()` (~15 lines)
2. `create_agent_tools()` (~80 lines) -- refactored to use `TOOL_TYPE_HANDLERS`
3. `create_function_tool()` (~80 lines)
4. `get_function_from_name()` (~35 lines)

**Total: ~250 lines** (down from 2,682).

#### 3.1 Refactor `create_agent_tools()` to use `TOOL_TYPE_HANDLERS`

Replace the 40-line `if/elif` chain (lines 88-130) with a dict lookup:

```python
from huf.ai.tool_types import TOOL_TYPE_HANDLERS

# In create_agent_tools(), replace the elif chain with:
function_path = TOOL_TYPE_HANDLERS.get(function_doc.types)
if not function_path:
	continue
```

#### 3.2 Clean Up Imports

Remove all imports that are no longer needed after extraction:
- `base64`, `save_file`, `requests`, `io` (moved to media handlers)
- `hashlib` (unused even now)
- `tool_functions` imports (moved to handlers/crud.py)
- Duplicate imports

Final imports for slimmed `sdk_tools.py`:
```python
import inspect
import json
import re
import asyncio
from typing import Any, Callable

import frappe
from frappe import _
from agents import FunctionTool

from huf.ai.tool_types import TOOL_TYPE_HANDLERS
from huf.ai.tool_registry import PermissionAwareToolRegistry
```

#### 3.3 Clean Up `on_invoke_tool` Closure

The `on_invoke_tool` closure in `create_function_tool()` (lines 280-343) has:
- Inline `import inspect` (already imported at module level)
- Complex parameter filtering logic

Simplify by extracting the parameter-filtering logic:

```python
def _call_with_filtered_args(func: Callable, args: dict):
	"""Call a function with only the parameters it accepts."""
	sig = inspect.signature(func)
	if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
		return func(**args)
	valid = set(sig.parameters.keys())
	return func(**{k: v for k, v in args.items() if k in valid})
```

This helper is also used in `flow_tool_executor.py` (lines 76-86), so it should live in a shared location (e.g., `sdk_tools.py` itself or a small `huf/ai/utils.py`).

---

### Phase 4: Fix Related Module Issues

#### 4.1 Fix `tool_functions.py` -- Remove Duplicate `attach_file_to_document`

Delete the first definition of `attach_file_to_document()` (lines 359-388) which is dead code overwritten by the second definition (line 461).

#### 4.2 Update `flow_tool_executor.py`

Replace the hardcoded `type_to_handler` dict (lines 121-143) with:

```python
from huf.ai.tool_types import TOOL_TYPE_HANDLERS, DOCTYPE_BOUND_TYPES
```

Replace `_inject_extra_args()` (lines 148-173) to use `DOCTYPE_BOUND_TYPES` instead of an inline list.

#### 4.3 Delete `conversation_data_tools.py`

This file is redundant with the handlers in `sdk_tools.py` (now `handlers/conversation_data.py`). Verify no imports reference it before deleting.

#### 4.4 Update `install.py` References

Update all `function_path` references in `huf/install.py`:
```python
# Before
"function_path": "huf.ai.sdk_tools.handle_generate_image"
# After
"function_path": "huf.ai.handlers.media.handle_generate_image"
```

Same for `handle_ocr_document`, `handle_generate_audio`, `handle_transcribe_audio`.

#### 4.5 Update `agent_chat.py` References

Update all `sdk_tools.handle_*` calls in `agent_chat.py` to use the new handler paths.

#### 4.6 Add Backward-Compatible Re-exports in `sdk_tools.py`

To avoid breaking any external references (e.g., existing `Agent Tool Function` documents in the database that store `function_path = "huf.ai.sdk_tools.handle_get_list"`), add re-exports:

```python
# sdk_tools.py - backward compatibility
# These handlers have moved to huf.ai.handlers.crud
# Re-exported here so existing tool function_path values continue to work.
from huf.ai.handlers.crud import (
	handle_get_list,
	handle_get_document,
	handle_create_document,
	handle_update_document,
	handle_delete_document,
	handle_get_documents,
	handle_create_documents,
	handle_update_documents,
	handle_delete_documents,
	handle_submit_document,
	handle_cancel_document,
	handle_get_value,
	handle_set_value,
	handle_get_report_result,
	handle_attach_file_to_document,
)
from huf.ai.handlers.conversation_data import (
	handle_get_conversation_data,
	handle_set_conversation_data,
	handle_load_conversation_data,
)
from huf.ai.handlers.media import (
	handle_generate_image,
	handle_ocr_document,
	handle_generate_audio,
	handle_transcribe_audio,
)
from huf.ai.handlers.agent_runner import handle_run_agent
```

**Reasoning**: Database records for `Agent Tool Function` may store `"huf.ai.sdk_tools.handle_get_list"` as their `function_path`. The `get_function_from_name()` resolver imports by dotted path, so these re-exports ensure old paths still resolve. New tool definitions should use the new paths via `tool_types.py`. The re-exports can be removed in a future migration.

---

### Phase 5: Code Quality Fixes (Applied During Extraction)

These are not separate steps but standards to apply during all extraction work:

#### 5.1 Consistent Indentation
All new and extracted code must use **tabs** per the project's ruff configuration. Fix any mixed tab/space indentation during extraction.

#### 5.2 Consistent `frappe.log_error()` Signature
Standardize to keyword arguments throughout:
```python
# Correct
frappe.log_error(title="SDK Tool Error", message=f"Failed: {e}")

# Incorrect (positional args, order varies across the codebase)
frappe.log_error(f"Failed: {e}", "SDK Tool Error")
frappe.log_error("SDK Tool Error", f"Failed: {e}")
```

#### 5.3 Remove `print()` Statements
`sdk_tools.py` line 1506 has `print("Returned images: ", images)`. Replace with `frappe.logger().debug(...)` or remove.

#### 5.4 Remove Bare `except: pass`
Replace with specific exception types and at minimum log the error.

#### 5.5 Remove Inline Imports
Move all imports to module level unless there's a genuine circular-import reason to keep them inline. Document any that must stay inline with a comment explaining why.

---

## Migration Strategy

### Database Compatibility
The critical constraint is that `Agent Tool Function` documents store `function_path` values like `"huf.ai.sdk_tools.handle_get_list"` in the database. These are resolved at runtime by `get_function_from_name()`.

**Approach**: Keep backward-compatible re-exports in `sdk_tools.py` (Phase 4.6). Optionally, add a data migration in `install.py` to update stored paths to new locations. The re-exports ensure zero downtime.

### Execution Order
1. **Phase 1** first (foundation, no breaking changes)
2. **Phase 2** next (extract handlers, add re-exports simultaneously)
3. **Phase 3** after Phase 2 (slim down sdk_tools.py)
4. **Phase 4** last (fix related modules)
5. **Phase 5** applied throughout all phases

Each phase can be a separate commit. The entire refactor can be done in a single PR.

---

## Before/After Summary

| Metric | Before | After |
|--------|--------|-------|
| `sdk_tools.py` lines | 2,682 | ~250 + re-exports |
| Tool-type mapping locations | 2 (sdk_tools + flow_tool_executor) | 1 (tool_types.py) |
| Duplicated media boilerplate | ~200 lines x4 | 0 (shared in media_utils.py) |
| Files with mixed indentation | 3+ | 0 |
| Dead code (unused factories) | ~170 lines | 0 |
| Duplicate function definitions | 1 (attach_file_to_document) | 0 |
| Duplicate helper files | 1 (conversation_data_tools.py) | 0 |
| Filename typos | 1 (cilent_side_tool.py) | 0 |

## Files Created
- `huf/ai/__init__.py`
- `huf/ai/tool_types.py`
- `huf/ai/media_utils.py`
- `huf/ai/handlers/__init__.py`
- `huf/ai/handlers/crud.py`
- `huf/ai/handlers/conversation_data.py`
- `huf/ai/handlers/media.py`
- `huf/ai/handlers/agent_runner.py`

## Files Modified
- `huf/ai/sdk_tools.py` (slimmed down + re-exports)
- `huf/ai/flow_tool_executor.py` (use tool_types.py)
- `huf/ai/tool_functions.py` (remove duplicate definition)
- `huf/ai/agent_chat.py` (update imports)
- `huf/install.py` (update function_path references)

## Files Deleted
- `huf/ai/conversation_data_tools.py` (redundant)
- `huf/ai/cilent_side_tool.py` (renamed to client_side_tool.py)

## Files Renamed
- `huf/ai/cilent_side_tool.py` → `huf/ai/client_side_tool.py`
