# Security Improvement Plans — Round 2

**Branch:** `doc/security-improvement-plans-2` (based on `develop`)  
**Planned at commit:** `acd025f`  
**Date:** 2026-06-14  
**Scope:** New and still-open security surfaces on the `develop` branch after the first security plan set (`doc/security-improvement-plans`, PR #302).

## Context

PR #302 (`plans/001-007`) already covers:

- SSRF in `validate_url` / HTTP redirect re-validation (001–002)
- `flow_webhook` fail-closed auth (003)
- ElevenLabs webhook signature verification + credential-length leak (004)
- Guest CRUD `reference_doctype` pinning (005)
- SVG artifact `dangerouslySetInnerHTML` sandboxing (006)
- `docs_renderer.py` path containment (007)

This document captures the **next round** of high-confidence security findings on `develop` (`acd025f`). It is intended to be merged as a planning/tracking PR; implementation of each item should happen in follow-up code PRs.

---

## How to use this plan

Each plan below follows the same structure:

- **Current state** — the exploitable pattern with a precise file/line reference.
- **Security goal** — what "fixed" looks like.
- **Feature preservation** — how to keep the legitimate feature working; this is the non-negotiable requirement that prevents over-restriction.
- **Concrete implementation** — copy/paste-able snippets and exact API choices.
- **STOP conditions / pitfalls** — things that look correct but are not.
- **Acceptance criteria** — tests and checks that must pass.
- **Verification** — the command(s) to run.

Adopt the execution order at the end of the summary table; dependencies are real.

---

## Summary table

| # | Finding | Category | Priority | Effort | Risk | Confidence |
|---|---------|----------|----------|--------|------|------------|
| 008 | Conversation mutation APIs lack authorization | security | P1 | M | HIGH | HIGH |
| 009 | `get_result_context` reads arbitrary DocTypes | security | P1 | S | HIGH | HIGH |
| 010 | `Huf Data Table` APIs bypass capability checks | security | P1 | S | MED | HIGH |
| 011 | `transcribe_audio` reads arbitrary File docs | security | P2 | S | LOW | MED |
| 012 | TTS/STT API keys written to `os.environ` | security | P2 | S | LOW | HIGH |
| 013 | `delete_documents` helper skips permission checks | security | P2 | S | LOW | HIGH |
| 014 | HTML/SVG artifacts run in same-origin context | security | P1 | S/M | HIGH | HIGH |
| 015 | JSX previews execute arbitrary JS via `react-jsx-parser` | security | P1 | M | HIGH | HIGH |
| 016 | Code-block fallback path injects raw HTML | security | P1 | S | MED | HIGH |
| 017 | HTML entity decoder uses `innerHTML` sink | security | P2 | S | MED | MED |
| 018 | `returnTo` navigation from `localStorage` not validated | security | P2 | S | MED | MED |
| 019 | Vulnerable frontend lockfile dependencies | security | P1 | S/M | HIGH | HIGH |
| 020 | Vulnerable Python direct/transitive dependencies | security | P1 | M | HIGH | HIGH |
| 021 | Hardcoded dev credentials in Docker/API docs | security | P3 | S | LOW | HIGH |

**Suggested execution order by leverage:** 008 → 009 → 014 → 015 → 016 → 019 → 020 → 010 → 018 → 017 → 011 → 012 → 013 → 021.

**Rationale for order:**

1. **008/009** close direct data-access bypasses that are reachable today from any authenticated session.
2. **014/015/016** close stored-XSS/code-execution sinks that can be triggered by any message an agent returns.
3. **019/020** remove known public exploits in the dependency tree before larger code changes widen the attack surface.
4. **010/018/017** are medium-risk hardening items that are cheap to land.
5. **011/012/013** are lower-severity backend hygiene.
6. **021** is documentation-only cleanup.

---

## Cross-cutting implementation rules

Apply these rules to every backend plan:

1. **Fail closed.** If a permission/capability check cannot be evaluated, return a permission error rather than proceeding.
2. **Do not swallow security exceptions.** `except Exception` that returns a generic success response is a bypass waiting to happen.
3. **Validate at the API layer, then again at the data layer if the function is reusable.** Defensive depth matters because whitelisted functions are also called from tools, schedulers, and hooks.
4. **Use Frappe primitives.** `frappe.has_permission`, `doc.check_permission()`, and `frappe.get_doc(...).as_dict(no_private_fields=True)` already apply field-level read permissions — prefer them over hand-rolled checks.
5. **Tests must cover the negative case.** A plan is not complete without a test that proves an unauthorized user is blocked.

Apply these rules to every frontend plan:

1. **Never render untrusted markup in the same origin.** `dangerouslySetInnerHTML` and inline `<script>` are only acceptable inside a sandboxed iframe without `allow-same-origin`.
2. **Defense in depth.** Sanitization + sandboxing, not sanitization alone.
3. **URLs that navigate must be validated or allow-listed.** Treat `localStorage`, query strings, and message content as untrusted.
4. **Agent-controlled metadata must not grant capabilities.** Fields like `interactive`, `trusted`, or `sandbox` in artifact JSON must not be used to weaken security controls.

---

## Verification commands

Backend:

```bash
cd /workspace/development/16
bench --site huf.localhost run-tests --app huf --module huf.ai.tests.test_security
```

Frontend:

```bash
cd frontend
yarn typecheck
yarn lint
yarn build
```

Dependencies:

```bash
cd frontend && npm audit --audit-level=high
cd .. && pip-audit --desc
```

---

## Plan 008 — Authorize conversation mutation APIs

**Priority:** P1 | **Effort:** M | **Risk:** HIGH | **Category:** security  
**Files in scope:**

- `huf/ai/agent_chat.py` (`send_message_to_conversation`, `upload_audio_and_transcribe_web`, `add_message`, `get_history`)
- `huf/ai/sdk_tools.py` (`handle_set_conversation_data`)
- `huf/ai/conversation_manager.py` (`ConversationManager.add_message`)
- `huf/ai/tests/test_security_conversation_auth.py` (create)

### Current state

`add_message()` loads a conversation by ID and inserts a message without verifying the caller owns it:

```python
# huf/ai/agent_chat.py:516-557
@frappe.whitelist()
def add_message(conversation_id: str, role: str, content: str, ...):
    conv_doc = frappe.get_doc("Agent Conversation", conversation_id)
    agent_name = conv_doc.agent
    cm = ConversationManager(agent_name=agent_name)
    msg = cm.add_message(
        conversation=conv_doc, role=role, content=content, ...
    )
```

`send_message_to_conversation` and `upload_audio_and_transcribe_web` have the same gap.  
`handle_set_conversation_data` writes `conversation_data` on the conversation doc with only a `conversation_id` check.

### Security goal

Only users who are legitimate participants in a conversation may append messages or mutate its state.

### Feature preservation

- Chat users must still be able to send text/audio to conversations they created.
- Agents must still be able to append their own messages during a run (the agent acts on behalf of the conversation owner).
- Guest chat flows (if enabled) must still work by creating a new conversation bound to the guest session.
- Admins/support users with `chat.view_all` may need read access; write access should still be limited to the owner/session to prevent support impersonation.

### Concrete implementation

Add a single shared helper in `huf/ai/agent_chat.py`:

```python
from frappe import _


def _assert_conversation_access(conversation, *, allow_read=False):
    """
    Fail closed if the current session cannot access *conversation*.

    Allowed:
      - The conversation owner (read + write).
      - A caller whose session_id matches the conversation's session_id
        (covers guest/anonymous chat sessions; read + write).
      - System Manager / Administrator for read operations only.
        Admin write access is intentionally NOT granted silently; admins
        should not impersonate chat users. If admin write is required,
        log an explicit audit entry.
    """
    user = frappe.session.user

    # Owner check
    if conversation.owner == user:
        return

    # Session-bound anonymous/guest check
    if conversation.session_id and conversation.session_id == frappe.session.sid:
        return

    # Admin read-only fallback
    if allow_read and (user == "Administrator" or "System Manager" in frappe.get_roles(user)):
        return

    frappe.throw(
        _("You do not have permission to access this conversation."),
        frappe.PermissionError,
    )
```

Call it at the top of every mutation entry point, and use `allow_read=True` for read-only endpoints:

```python
@frappe.whitelist()
def send_message_to_conversation(conversation: str, message: str):
    if not conversation:
        frappe.throw(_("conversation is required"))
    if not message:
        frappe.throw(_("message is required"))

    conv_doc = frappe.get_doc("Agent Conversation", conversation)
    _assert_conversation_access(conv_doc)
    ...


@frappe.whitelist()
def get_history(conversation_id: str = None, limit: int = 200):
    if not conversation_id:
        return []
    conv_doc = frappe.get_doc("Agent Conversation", conversation_id)
    _assert_conversation_access(conv_doc, allow_read=True)
    ...
```

For `handle_set_conversation_data` in `huf/ai/sdk_tools.py`:

```python
def handle_set_conversation_data(name, value, ..., conversation_id=None, **kwargs):
    if not conversation_id:
        return {"success": False, "error": "No conversation context provided"}

    conversation = frappe.get_doc("Agent Conversation", conversation_id)
    _assert_conversation_access(conversation)
    ...
```

Either import `_assert_conversation_access` from `agent_chat` or duplicate a small helper in `sdk_tools.py` to avoid a circular import. The key is that **the same policy is enforced in both places**.

Inside `ConversationManager.add_message`, the `ignore_permissions=True` insert is acceptable **only because** the API layer has already authorized the caller. Add an explicit comment to that effect:

```python
# Authorization happens at the API layer (see _assert_conversation_access).
# ignore_permissions is required because Agent Message insert permissions
# are intentionally restrictive for the agent-run worker context.
message.insert(ignore_permissions=True)
```

### STOP conditions / pitfalls

- **Do NOT check only `frappe.session.user != 'Guest'`.** Authenticated user A can still attack user B.
- **Do NOT trust the `session_id` from the request body.** It must come from `frappe.session.sid`.
- **Do NOT make admins silently exempt from write checks** unless a separate audit log is added.
- **Do NOT place the check only in `send_message_to_conversation` and forget `add_message`/`upload_audio_and_transcribe_web`/`get_history`/`handle_set_conversation_data`.

### Acceptance criteria

- Owner can mutate their own conversation and read its history.
- Another authenticated user cannot mutate someone else's conversation or read its history (receives `PermissionError`).
- A guest cannot mutate an authenticated user's conversation or read its history.
- A guest can still mutate a conversation created during their guest session.
- Admin can read any conversation history (`allow_read=True`) but cannot silently mutate it.
- Existing chat tests still pass.

### Verification

- `bench --site huf.localhost run-tests --module huf.ai.tests.test_security_conversation_auth` → all pass.
- Existing chat tests still pass.

---

## Plan 009 — Restrict `get_result_context` to allowed DocTypes and permissions

**Priority:** P1 | **Effort:** S | **Risk:** HIGH | **Category:** security  
**Files in scope:**

- `huf/ai/sdk_tools.py` (`handle_get_result_context`)
- `huf/ai/tests/test_security_context.py` (create)

### Current state

```python
# huf/ai/sdk_tools.py:1347-1383
def handle_get_result_context(reference_doctype: str, reference_name: str, **kwargs):
    if not frappe.db.exists(reference_doctype, reference_name):
        return {"success": False, "error": "..."}
    doc = frappe.get_doc(reference_doctype, reference_name)
    # ... returns doc.as_dict() for arbitrary doctypes
```

No permission check restricts the DocType or document. The function has special-case handling for `Agent Tool Call` and `Agent Context Artifact`, but then falls through to returning `doc.as_dict()` for **any** DocType.

### Security goal

`get_result_context` must only return data the caller is allowed to read, and only for DocTypes that are intentionally exposed by this tool.

### Feature preservation

- Agents must still be able to fetch tool results and context artifacts by reference handle.
- The tool should remain useful for "out-of-band" references: large payloads that were intentionally stored for later retrieval.
- General-purpose document lookup should be handled by the existing `get_document` tool, which already calls `doc.check_permission()`.

### Concrete implementation

Replace the fall-through with an explicit allow-list and permission check:

```python
ALLOWED_RESULT_CONTEXT_DOCTYPES = {
    "Agent Tool Call",
    "Agent Context Artifact",
}


def handle_get_result_context(reference_doctype: str, reference_name: str, **kwargs):
    if not reference_doctype or not reference_name:
        return {"success": False, "error": "Both reference_doctype and reference_name are required."}

    if reference_doctype not in ALLOWED_RESULT_CONTEXT_DOCTYPES:
        frappe.log_error(
            f"get_result_context rejected for {reference_doctype}",
            "Security: get_result_context allow-list"
        )
        return {"success": False, "error": f"DocType '{reference_doctype}' is not accessible via get_result_context."}

    if not frappe.db.exists(reference_doctype, reference_name):
        return {"success": False, "error": f"Document {reference_name} of type {reference_doctype} not found."}

    doc = frappe.get_doc(reference_doctype, reference_name)

    # Enforce Frappe read permissions and field-level read permissions.
    if not frappe.has_permission(reference_doctype, "read", doc=doc):
        return {"success": False, "error": f"You do not have permission to read {reference_doctype} {reference_name}."}

    if reference_doctype == "Agent Tool Call":
        return {
            "success": True,
            "tool": doc.tool,
            "tool_args": doc.tool_args,
            "status": doc.status,
            "tool_result": doc.tool_result,
            "error_message": doc.error_message,
        }

    if reference_doctype == "Agent Context Artifact":
        return {
            "success": True,
            "artifact_type": doc.artifact_type,
            "summary": doc.summary,
            "payload_json": doc.payload_json,
            "reference_doctype": doc.reference_doctype,
            "reference_name": doc.reference_name,
        }

    # Unreachable because of the allow-list, but kept as defense-in-depth.
    return {"success": False, "error": "Unexpected DocType."}
```

### STOP conditions / pitfalls

- **Do NOT use `doc.as_dict()` without `no_private_fields=True` or `doc.apply_fieldlevel_read_permissions()`.** Password fields and other private data may leak otherwise.
- **Do NOT allow-list broad DocTypes like `User`, `AI Provider`, or `Agent Message`.**
- **Do NOT rely on the agent-tool schema to prevent abuse.** An attacker with a whitelisted account can call the underlying whitelisted function directly.

### Acceptance criteria

- Fetching an `Agent Tool Call` the caller can read returns the expected payload.
- Fetching an `Agent Tool Call` the caller cannot read returns a permission error.
- Fetching `User`, `AI Provider`, or any other non-allow-listed DocType returns an allow-list error.

### Verification

- New tests pass.
- Attempting to fetch `User`/`AI Provider` via the tool returns a permission error.

---

## Plan 010 — Add capability checks to Huf Data Table management APIs

**Priority:** P1 | **Effort:** S | **Risk:** MED | **Category:** security  
**Files in scope:**

- `huf/huf/doctype/huf_data_table/api.py`
- `huf/permissions.py` (add capability)
- `huf/ai/tests/test_security_data_table.py` (create)

### Current state

```python
# huf/huf/doctype/huf_data_table/api.py:75
dt.insert(ignore_permissions=True)
# :126
dt.save(ignore_permissions=True)
# :156-158
frappe.delete_doc("DocType", doctype_name, force=True, ignore_permissions=True)
frappe.delete_doc("Huf Data Table", name, ignore_permissions=True)
```

No Huf capability check is performed before mutating custom DocTypes. Any authenticated user with access to the whitelisted API can create, modify, or delete data tables.

### Security goal

Only users with an explicit data-table management capability can alter the schema of Huf Data Tables.

### Feature preservation

- Regular users must still be able to read and write records inside data tables they have permission for.
- Only the *schema-management* endpoints (`create_data_table`, `update_data_table`, `delete_data_table`) need the new capability.
- Listing and record APIs (`get_table_schema`, `get_table_record_counts`, and the generic CRUD endpoints used by the table UI) should remain governed by standard DocType permissions.

### Concrete implementation

1. Add a new capability in `huf/permissions.py`:

```python
CAPABILITIES: dict[str, str] = {
    ...
    # --- Data Tables ---
    "data_tables.manage": "Manage Data Tables",
    ...
}
```

Add it to the default roles that should have it (at minimum `Huf Admin`; consider `Huf Manager`):

```python
"Huf Manager": [
    ...
    "data_tables.manage",
    ...
]
```

2. Add a helper in `huf/huf/doctype/huf_data_table/api.py`:

```python
from huf.permissions import has_capability
from frappe import _


def _require_data_table_manager():
    if not has_capability(frappe.session.user, "data_tables.manage"):
        frappe.throw(_("Not permitted to manage data tables."), frappe.PermissionError)
```

3. Gate the three mutation endpoints at the very top:

```python
@frappe.whitelist()
def create_data_table(...):
    _require_data_table_manager()
    ...

@frappe.whitelist()
def update_data_table(...):
    _require_data_table_manager()
    ...

@frappe.whitelist()
def delete_data_table(name: str) -> dict:
    _require_data_table_manager()
    ...
```

4. Existing installs need the new capability added to roles that should have it. Create a patch:

```python
# huf/patches/v1/add_data_table_manage_capability.py
import frappe
from huf.permissions import DEFAULT_ROLE_CAPABILITIES


def execute():
    for role_name, caps in DEFAULT_ROLE_CAPABILITIES.items():
        if "data_tables.manage" not in caps:
            continue
        if not frappe.db.exists("Huf Role", role_name):
            continue
        doc = frappe.get_doc("Huf Role", role_name)
        existing = {row.capability for row in doc.permissions}
        if "data_tables.manage" in existing:
            continue
        doc.append("permissions", {"capability": "data_tables.manage"})
        doc.save(ignore_permissions=True)
    frappe.db.commit()
```

Register the patch in `huf/patches.txt`:

```text
huf.patches.v1.add_data_table_manage_capability
```

5. The read helpers (`get_table_schema`, `get_table_record_counts`) should remain open to any user who can read `Huf Data Table` records, but they must not leak schema information to anonymous users. Add a standard `frappe.has_permission("Huf Data Table", "read", doc=name)` check at the top of each.

### STOP conditions / pitfalls

- **Do NOT reuse `flows.manage` just because it is convenient.** Schema management is a distinct privilege.
- **Do NOT check capability only on create and forget update/delete.** All three mutation endpoints must be gated.
- **Do NOT forget the install/seed path.** Add the capability to `huf/permissions.py` and create a patch (`huf/patches/v1/add_data_table_manage_capability.py`) for existing installs.
- **Do NOT leave `get_table_schema` / `get_table_record_counts` ungated.** They should require `read` permission on `Huf Data Table` even though they do not need `data_tables.manage`.

### Acceptance criteria

- User with `data_tables.manage` can create/update/delete tables.
- User without the capability receives `PermissionError` for all three operations.
- Existing data-table CRUD operations on records remain unaffected.

### Verification

- Tests pass.
- Calling endpoint as a non-authorized user returns 403 / permission error.

---

## Plan 011 — Enforce file permission checks in `transcribe_audio`

**Priority:** P2 | **Effort:** S | **Risk:** LOW | **Category:** security  
**Files in scope:**

- `huf/ai/sdk_tools.py` (`handle_transcribe_audio`)
- `huf/ai/tests/test_security_transcribe.py` (create)

### Current state

`handle_transcribe_audio` accepts `file_id`/`file_url` and opens the file without checking `File` read permission or attachment ownership.

### Security goal

Only users who are allowed to read a file can have it transcribed.

### Feature preservation

- Users must still be able to transcribe audio files they uploaded to a chat conversation.
- Agents must still be able to transcribe files attached to messages in the current conversation.
- Direct `file_url` inputs are convenience shortcuts; if they cannot be safely resolved, reject them rather than silently proceeding.

### Concrete implementation

After resolving `file_doc`, enforce read permission and an ownership/attachment check:

```python
# After file_doc is resolved
if not frappe.has_permission("File", "read", doc=file_doc.name):
    return {"success": False, "error": "Permission denied for file."}

# Defense-in-depth: ensure the file is attached to an entity the caller can access.
attached_to_doctype = file_doc.attached_to_doctype
attached_to_name = file_doc.attached_to_name

if attached_to_doctype and attached_to_name:
    if attached_to_doctype == "Agent Message":
        message = frappe.get_doc("Agent Message", attached_to_name)
        conversation = frappe.get_doc("Agent Conversation", message.conversation)
        _assert_conversation_access(conversation)  # reuse plan 008 helper
    elif not frappe.has_permission(attached_to_doctype, "read", doc=attached_to_name):
        return {"success": False, "error": "Permission denied for attached document."}
else:
    # File is not attached to anything; require ownership.
    if file_doc.owner != frappe.session.user:
        return {"success": False, "error": "Permission denied for unattached file."}
```

For `file_url`, reject absolute URLs and any path outside the Frappe file store. Only allow resolving `file_url` values that map to a `File` doc in the local store:

```python
if file_url:
    # Reject remote URLs and protocol-relative URLs outright.
    stripped = file_url.strip().lower()
    if stripped.startswith(("http://", "https://", "//")):
        return {"success": False, "error": "Remote file_url is not allowed."}

    file_doc = frappe.get_all(
        "File",
        filters={"file_url": file_url},
        limit=1,
    )
    if not file_doc:
        return {"success": False, "error": f"File not found at URL: {file_url}"}
    file_doc = frappe.get_doc("File", file_doc[0].name)
```

### STOP conditions / pitfalls

- **Do NOT check only `File` read permission.** Frappe file permissions can be coarse; combine with attachment ownership.
- **Do NOT allow `file_url` to be an arbitrary HTTP(S) URL.** That reintroduces SSRF through the transcription endpoint.
- **Do NOT skip the check when `ignore_permissions=True` is passed by a tool.** `handle_transcribe_audio` is a whitelisted function; it should not trust tool-level flags.

### Acceptance criteria

- Authorized file access succeeds.
- Unauthorized file access returns a permission error.
- `file_url` pointing outside the Frappe file store is rejected.

### Verification

- Regression tests for authorized and unauthorized file access pass.

---

## Plan 012 — Remove TTS/STT API key leakage via `os.environ`

**Priority:** P2 | **Effort:** S | **Risk:** LOW | **Category:** security  
**Files in scope:**

- `huf/ai/sdk_tools.py` (`handle_generate_audio`, `handle_transcribe_audio`)

### Current state

```python
# huf/ai/sdk_tools.py:2409-2411
if provider_name in _TTS_ENV_VAR_PROVIDERS:
    import os
    os.environ[_TTS_ENV_VAR_PROVIDERS[provider_name]] = api_key
```

API keys are written to the process environment, where they may leak to child processes or logs.

### Security goal

Provider API keys must only be passed through explicit parameters to LiteLLM, never persisted in `os.environ`.

### Feature preservation

- TTS/STT must continue to work for all providers currently supported via `_TTS_ENV_VAR_PROVIDERS`.
- The `_resolve_tts_config` / `_resolve_stt_config` helpers must continue to pick the right model and API key (including cross-provider TTS via the agent's `tts_model`).

### Concrete implementation

LiteLLM's `speech()` and `transcription()` accept an `api_key` parameter directly. Pass it explicitly:

```python
speech_params = {
    "model": normalized_model,
    "input": input_text,
    "voice": voice,
    "speed": speed,
    "response_format": response_format,
    "api_key": api_key,
}

if provider_name == "openai" and base_url:
    speech_params["api_base"] = base_url

response = await litellm.speech(**speech_params)
```

For transcription:

```python
transcription_params = {
    "model": normalized_model,
    "file": file_path,
    "api_key": api_key,
}
response = await litellm.transcription(**transcription_params)
```

Then delete the `os.environ` assignment entirely. If a provider *absolutely* requires an environment variable (verify in LiteLLM docs), wrap it in a narrow context:

```python
import os
old = os.environ.get(env_var)
try:
    os.environ[env_var] = api_key
    response = await litellm.speech(...)
finally:
    if old is None:
        os.environ.pop(env_var, None)
    else:
        os.environ[env_var] = old
```

This pattern must only be used as a last resort and documented with a code comment explaining why.

### STOP conditions / pitfalls

- **Do NOT leave the key in `os.environ` after the call returns.** Child processes spawned later would inherit it.
- **Do NOT assume `litellm.speech` ignores `api_key`.** Test each provider after the change.
- **Do NOT log `speech_params` or `transcription_params` without redacting `api_key`.**

### Acceptance criteria

- TTS/STT tests still pass.
- No `os.environ[...] = api_key` patterns remain in `huf/ai/sdk_tools.py`.
- A grep for `os\.environ\[` across `huf/ai/sdk_tools.py` related to TTS/STT returns no matches.
- Add a unit test that mocks `litellm.speech` / `litellm.transcription` and asserts the API key is passed via the `api_key` parameter and is not present in `os.environ` after the call returns.

### Verification

- TTS/STT tests still pass.
- `grep -R "os\.environ\[" huf/ai/sdk_tools.py` shows no TTS/STT API-key assignments.

---

## Plan 013 — Add per-document permission check in `delete_documents`

**Priority:** P2 | **Effort:** S | **Risk:** LOW | **Category:** security  
**Files in scope:**

- `huf/ai/tool_functions.py` (`delete_documents`)
- `huf/ai/tests/test_security_bulk_delete.py` (create)

### Current state

```python
# huf/ai/tool_functions.py:193-199
def delete_documents(doctype: str, document_ids: list):
    """
    Delete documents from the database
    """
    for document_id in document_ids:
        frappe.delete_doc(doctype, document_id)
    return {"document_ids": document_ids, "message": "Documents deleted", "doctype": doctype}
```

No per-document delete permission check.

### Security goal

Each document in a bulk-delete list must be individually authorized.

### Feature preservation

- Agents must still be able to delete multiple records when the user has delete permission on each one.
- Partial failure must be reported so the agent can retry or inform the user.

### Concrete implementation

Mirror the pattern already used in `handle_delete_document`:

```python
def delete_documents(doctype: str, document_ids: list):
    deleted = []
    failed = []

    for document_id in document_ids:
        if not frappe.has_permission(doctype, "delete", doc=document_id):
            failed.append({
                "name": document_id,
                "error": f"You do not have delete permission on {doctype} {document_id}",
                "permission_denied": True,
            })
            continue

        try:
            frappe.delete_doc(doctype, document_id)
            deleted.append(document_id)
        except frappe.PermissionError as e:
            failed.append({
                "name": document_id,
                "error": str(e),
                "permission_denied": True,
            })
        except Exception as e:
            failed.append({"name": document_id, "error": str(e)})

    return {
        "doctype": doctype,
        "deleted": deleted,
        "failed": failed,
        "message": f"Deleted {len(deleted)} of {len(document_ids)} documents.",
    }
```

### STOP conditions / pitfalls

- **Do NOT fail the entire batch because one document is unauthorized.** That would be a denial-of-service vector against legitimate bulk deletes.
- **Do NOT skip the check when the tool is called by an agent.** The agent is acting on behalf of a user; Frappe permissions must still apply.
- **Do NOT swallow `PermissionError` as a generic failure.** Distinguish permission errors so callers and logs can identify authorization issues.

### Acceptance criteria

- Bulk delete succeeds when the user has delete permission on all documents.
- Unauthorized documents are reported in `failed` without stopping the batch.
- Test for unauthorized bulk delete fails before fix and passes after.

### Verification

- `bench --site huf.localhost run-tests --module huf.ai.tests.test_security_bulk_delete` → all pass.

---

## Plan 014 — Harden HTML/SVG artifact rendering

**Priority:** P1 | **Effort:** S/M | **Risk:** HIGH | **Category:** security  
**Files in scope:**

- `frontend/src/components/chat/ArtifactRenderer.tsx`
- `frontend/src/utils/artifactParser.ts`

### Current state

```tsx
// ArtifactRenderer.tsx:172-178
case 'html':
  return <iframe srcDoc={artifact.content} sandbox="allow-scripts" ... />;

// ArtifactRenderer.tsx:190-196
case 'svg':
  return <div dangerouslySetInnerHTML={{ __html: artifact.content }} />;
```

SVG is injected unsanitized; HTML iframe defaults to `allow-scripts`.

### Security goal

Untrusted HTML/SVG content must run in an isolated, sandboxed origin where it cannot access the parent document's cookies, localStorage, or session.

### Feature preservation

- Static HTML previews must still render CSS and basic layout.
- SVG diagrams must still render visually.
- Full-screen artifact preview (`/huf/view/:messageId`) must continue to work.
- Note: interactive HTML widgets that require `allow-scripts` are intentionally out of scope for this plan. They require a separate design that includes explicit user consent and a sandbox without `allow-same-origin`.

### Concrete implementation

1. Render SVG inside a sandboxed iframe:

```tsx
case 'svg':
  return (
    <div className="flex flex-col gap-2">
      <iframe
        srcDoc={artifact.content}
        sandbox=""
        className="w-full h-96 border rounded bg-white"
        title={artifact.title || 'SVG Preview'}
      />
      ...
    </div>
  );
```

2. Default the HTML iframe sandbox to empty. Do **not** allow agent-controlled metadata to enable scripts:

```tsx
case 'html':
  return (
    <div className="flex flex-col gap-2">
      <iframe
        srcDoc={artifact.content}
        sandbox=""
        className="w-full h-96 border rounded bg-white"
        title={artifact.title || 'HTML Preview'}
      />
      ...
    </div>
  );
```

If interactive HTML widgets are required later, they must be implemented as a separate feature with:
- explicit user opt-in per artifact, and
- a sandbox that still lacks `allow-same-origin`.

3. As defense-in-depth, sanitize SVG with DOMPurify's SVG profile before rendering:

```ts
import DOMPurify from 'dompurify';

const sanitizedSvg = DOMPurify.sanitize(artifact.content, { USE_PROFILES: { svg: true } });
```

DOMPurify cannot make inline SVG safe on the same origin, so the iframe sandbox remains the primary control.

### STOP conditions / pitfalls

- **Do NOT add `allow-same-origin` to the sandbox.** That would let the iframe read parent-origin storage even with `allow-scripts` disabled.
- **Do NOT enable `allow-scripts` based on agent-controlled metadata.** An attacker who can influence artifact JSON would simply set `interactive: true`.
- **Do NOT rely on DOMPurify alone.** Mutation-based SVG XSS can bypass static sanitizers.
- **If plan 006 from PR #302 has already merged, verify that SVG no longer uses `dangerouslySetInnerHTML` before re-applying changes.** Plan 006 partially overlaps with this plan.

### Acceptance criteria

- `yarn typecheck` and `yarn build` pass.
- SVG artifacts render inside an iframe with `sandbox=""`.
- HTML artifacts default to `sandbox=""`.
- A test asserts no `dangerouslySetInnerHTML` is used for SVG.

### Verification

- `yarn typecheck` and `yarn build` pass.
- Existing artifact rendering tests (if any) pass; add a test that asserts no `dangerouslySetInnerHTML` for SVG.

---

## Plan 015 — Sandbox JSX previews to prevent arbitrary JS execution

**Priority:** P1 | **Effort:** M–H | **Risk:** HIGH | **Category:** security  
**Files in scope:**

- `frontend/src/components/ui/jsx-preview.tsx`
- `frontend/src/components/chat/JSXPreviewRenderer.tsx` (if it wraps the component)

### Current state

```tsx
// jsx-preview.tsx:477-488
<JsxParser
  jsx={processedJsx}
  components={{ ...availableComponents, ...components }}
  bindings={{ ...defaultBindings, ...bindings }}
  allowUnknownElements={false}
/>
```

`react-jsx-parser` evaluates inline expressions via `new Function(...)`. `defaultBindings` exposes `Object`, `Array`, `console`, etc., enabling stored XSS / arbitrary JS execution.

### Security goal

JSX previews must be rendered in a context where malicious code cannot access the parent origin or exfiltrate data.

### Feature preservation

- Recharts, shadcn/ui, and Lucide icon components must still render inside previews.
- Standard bindings like `useState`, chart data arrays, and helper values must still work.
- Export-to-PNG/SVG must still work for chart previews.

### Concrete implementation

The only robust fix is to move JSX execution out of the parent origin. There are two viable approaches:

**Option A — sandboxed iframe (recommended, higher effort):**

Move JSX execution into a separate origin-less sandbox. The cleanest approach is a dedicated route (e.g., `/huf/jsx-sandbox`) that receives JSX and bindings via `postMessage` and renders it inside an iframe with `sandbox="allow-scripts"` (no `allow-same-origin`).

Implementation sketch:

1. Create `frontend/src/pages/JsxSandboxPage.tsx` that listens for `postMessage`, validates the origin of messages (`event.origin === window.location.origin`), and renders the JSX with `react-jsx-parser`.
2. `JSXPreviewContent` renders an iframe whose `src` is `/huf/jsx-sandbox`.
3. After mounting, post the JSX string and a sanitized bindings object into the iframe.
4. Export-to-PNG/SVG runs inside the iframe; the resulting blob is posted back to the parent via `postMessage`.

Do **not** use `renderToStaticMarkup` as the iframe `srcDoc` — hooks and dynamic bindings do not survive static serialization.

Challenges:

- Component imports must be available inside the sandbox bundle.
- The export-to-PNG feature must be refactored to work across the iframe boundary.
- Because this is a larger change, treat it as a dedicated implementation PR.

**Option B — replace `react-jsx-parser` with a safe renderer:**

If the iframe proves too invasive for this PR, add immediate defense-in-depth while planning the iframe migration:

```tsx
const safeBindings = {
  ...defaultBindings,
  Object: undefined,
  Array: undefined,
  console: undefined,
  eval: undefined,
  Function: undefined,
};

<JsxParser
  jsx={processedJsx}
  components={{ ...availableComponents, ...components }}
  bindings={safeBindings}
  blacklistedAttrs={[/^on[A-Z]/i]}
  allowUnknownElements={false}
  renderError={(err) => { ... }}
/>
```

This reduces but does not eliminate the risk, because `react-jsx-parser` still uses `new Function`. It is a temporary hardening measure, not a complete fix.

**Recommended path:** implement Option A for artifact/chat JSX previews. If Option B is used as a stopgap, create a follow-up issue titled "Migrate JSX previews to sandboxed iframe" before the stopgap PR is merged, and link it in the plan status.

### STOP conditions / pitfalls

- **Do NOT add `allow-same-origin` to the JSX iframe sandbox.** That would let malicious JSX read parent cookies/localStorage.
- **Do NOT expose `window`, `document`, `fetch`, or `localStorage` in bindings.**
- **Do NOT rely on `blacklistedAttrs` alone.** It helps but does not prevent arbitrary JS via JSX expressions.

### Acceptance criteria

- JSX preview runs in an iframe without `allow-same-origin`, OR the renderer no longer uses `new Function`.
- Malicious JSX payloads cannot access `window.parent.document.cookie` in tests.
- Existing chart/component previews still render.

### Verification

- `yarn typecheck` / `yarn build` pass.
- New sandbox tests pass.

---

## Plan 016 — Harden code-block rendering against XSS fallback

**Priority:** P1 | **Effort:** S | **Risk:** MED | **Category:** security  
**Files in scope:**

- `frontend/src/components/ai-elements/code-block.tsx`

### Current state

```tsx
// code-block.tsx:72-74
<pre
  className={`language-${language} ...`}
  dangerouslySetInnerHTML={{ __html: html || code }}
/>
```

If `Prism.highlight` throws, the raw `code` string is injected as HTML.

### Security goal

Code blocks must render code as text, not HTML, unless the highlighted output is explicitly sanitized.

### Feature preservation

- Syntax highlighting via Prism/Shiki must continue to work.
- Line numbers and language labels must remain.
- Copy-to-clipboard must still function.

### Concrete implementation

1. Pass the highlighted HTML through DOMPurify before assignment:

```tsx
import DOMPurify from 'dompurify';

const sanitizedHtml = useMemo(() => {
  if (!html) return '';
  // Prism output is structural spans; restrict to the smallest surface.
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['span', 'code', 'pre', 'br'],
    ALLOWED_ATTR: ['class'],
  });
}, [html]);
```

2. Escape the fallback `code` path instead of injecting it raw:

```tsx
<pre
  className={`language-${language} overflow-x-auto p-4 text-sm font-mono m-0`}
  dangerouslySetInnerHTML={{ __html: sanitizedHtml || escapeHtml(code) }}
/>
```

Where `escapeHtml` is:

```ts
function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
```

### STOP conditions / pitfalls

- **Do NOT leave `dangerouslySetInnerHTML={{ __html: html || code }}` unchanged.** Even if Prism rarely throws, the fallback is a direct XSS sink.
- **Do NOT allow DOMPurify to keep arbitrary tags/attributes.** Prism output only needs structural markup (`span`/`code`/`pre`) with `class`. Verify the allowed tag list against actual Shiki/Prism output in the project.

### Acceptance criteria

- Code containing `<script>alert(1)</script>` is rendered as text, not executed.
- If Prism throws, the raw code is escaped, not injected.
- `yarn build` passes.

### Verification

- `yarn build` passes.
- Regression test passes.

---

## Plan 017 — Replace HTML-parser entity decoder with pure string replacement

**Priority:** P2 | **Effort:** S | **Risk:** MED | **Category:** security  
**Files in scope:**

- `frontend/src/components/chat/MessageContentWithArtifacts.tsx`
- `frontend/src/pages/PreviewViewPage.tsx`

### Current state

```ts
// MessageContentWithArtifacts.tsx:29-31
const textarea = document.createElement('textarea');
textarea.innerHTML = text;
return textarea.value;
```

Parsing untrusted content through `innerHTML` is a mutation-XSS sink.

### Security goal

Decode HTML entities without using the DOM HTML parser.

### Feature preservation

- Artifact tags like `<web-preview>`, `<jsx-preview>`, and `<artifact>` must still be decoded from `&lt;` / `&gt;` entities.
- Standard HTML entities (`&amp;`, `&quot;`, `&#39;`) must decode correctly.
- SSR must still work (the file already has an SSR branch).

### Concrete implementation

The SSR branch already contains the correct implementation. Promote it to the only path:

```ts
function decodeHtmlEntities(text: string): string {
  // Order matters: decode &amp; last to avoid double-decoding inputs like &amp;lt;.
  return text
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, '&');
}
```

Apply the same function in both `MessageContentWithArtifacts.tsx` and `PreviewViewPage.tsx`, and remove the `textarea.innerHTML` branch.

### STOP conditions / pitfalls

- **Do NOT try to support every HTML entity in existence.** Only the five entities used by the artifact encoding path are needed.
- **Do NOT leave the `textarea.innerHTML` fallback for legacy browsers.** Modern browsers support the string replacement path perfectly.

### Acceptance criteria

- Existing message-content tests pass.
- New decoder tests pass for all five entities and combinations.

### Verification

- Existing message-content tests pass.
- New decoder tests pass.

---

## Plan 018 — Validate `returnTo` navigation from `localStorage`

**Priority:** P2 | **Effort:** S | **Risk:** MED | **Category:** security  
**Files in scope:**

- `frontend/src/pages/AgentPromptFormPage.tsx`

### Current state

```ts
// AgentPromptFormPage.tsx:263-267
const returnTo = state?.returnTo || fallback?.returnTo;
if (returnTo) {
  navigate(returnTo, { replace: true });
}
```

`returnTo` from `localStorage` is passed directly to `navigate`.

### Security goal

Reject attacker-controlled `returnTo` values that could lead to open redirect or XSS.

### Feature preservation

- The "create prompt and return to agent form" flow must still work.
- Internal paths like `/huf/agents/:id?tab=general` must continue to be navigable.

### Concrete implementation

Add a validation helper:

```ts
const HUF_PATH_PREFIX = '/huf/';

function isInternalPath(path: string): boolean {
  try {
    const url = new URL(path, window.location.origin);
    // Reject absolute URLs, protocol-relative URLs, and different origins.
    if (url.origin !== window.location.origin) return false;
    // Reject dangerous schemes.
    if (!['http:', 'https:'].includes(url.protocol)) return false;
    // Strip javascript: / data: even if encoded.
    const decoded = decodeURIComponent(path);
    if (/^(javascript|data|vbscript):/i.test(decoded)) return false;
    // Allow only paths under the Huf app prefix. `new URL` normalizes `..` so
    // paths like /huf/agents/../../evil are rejected.
    return url.pathname.startsWith(HUF_PATH_PREFIX);
  } catch {
    return false;
  }
}
```

Then:

```ts
if (returnTo && isInternalPath(returnTo)) {
  navigate(returnTo, { replace: true });
}
```

If `returnTo` fails validation, fall back to a safe default (e.g., the prompts list) and log a warning.

### STOP conditions / pitfalls

- **Do NOT only strip `javascript:` as a string prefix.** `jAvaScript:`, `\x6aavascript:`, and newline tricks bypass naive filters.
- **Do NOT allow arbitrary absolute URLs even on the same origin.** Restrict to the Huf app prefix.
- **Do NOT throw a visible error for invalid `returnTo`.** Silently falling back to a safe route is better UX and avoids leaking information.
- **Do NOT fix only one call site.** The same pattern appears in at least two places in `AgentPromptFormPage.tsx` (around lines 263 and 310); apply the validator to both.

### Acceptance criteria

- Valid internal `returnTo` values (e.g., `/huf/agents/:id?tab=general`) navigate correctly.
- `javascript:alert(1)`, `https://evil.com`, `/evil`, and `/huf/agents/../../evil` are rejected.
- Both call sites in `AgentPromptFormPage.tsx` use the validator.
- `yarn typecheck` passes.

### Verification

- `yarn typecheck` passes.
- Malicious `returnTo` values are rejected.

---

## Plan 019 — Upgrade vulnerable frontend lockfile dependencies

**Priority:** P1 | **Effort:** S/M | **Risk:** HIGH | **Category:** security  
**Files in scope:**

- `frontend/package-lock.json`
- `frontend/yarn.lock`
- `frontend/package.json` (constraints if needed)
- `.github/workflows/*.yml` (CI addition)

### Current state

HIGH-severity advisories exist in the frontend dependency tree, including `react-router` and `ai` SDK transitive packages. `package.json` pins `react-router-dom@^7.9.4` and `ai@^6.0.116`, but the lockfile(s) may resolve older/vulnerable versions. Note that the repository currently contains **both** `frontend/package-lock.json` and `frontend/yarn.lock`, which can diverge and produce different installed trees.

### Security goal

Eliminate known HIGH/CRITICAL severity vulnerabilities in frontend dependencies and use a single, authoritative lockfile.

### Feature preservation

- All routes in `App.tsx` must continue to work.
- AI SDK streaming hooks (`useChat`) must continue to function.
- Build and typecheck must pass.

### Concrete implementation

1. **Standardize on one package manager.** The build scripts use `yarn` (`yarn copy-html-entry`), so `yarn` is the natural choice. Remove `package-lock.json` and keep `yarn.lock` as the single source of truth. If the team prefers `npm`, remove `yarn.lock` instead and update build scripts consistently. Do not keep both.

2. Regenerate the chosen lockfile:

```bash
cd frontend
# If using yarn:
rm package-lock.json
yarn install

# If using npm:
rm yarn.lock
npm install
```

3. Run the chosen package manager's audit and fix commands:

```bash
# yarn
yarn audit --level high
# or npm
npm audit --audit-level=high
npm audit fix
```

If a vulnerability cannot be auto-fixed without a major version bump, update `package.json` constraints manually and document the breaking-change review.

4. Verify routing in `App.tsx` and the build still work:

```bash
yarn typecheck
yarn lint
yarn build
```

5. Add the audit step to CI. Example for GitHub Actions (adjust for yarn or npm):

```yaml
- name: Audit frontend dependencies
  working-directory: frontend
  run: npm audit --audit-level=high
```

### STOP conditions / pitfalls

- **Do NOT keep both `package-lock.json` and `yarn.lock`.** Divergent lockfiles cause different dependency trees on different machines.
- **Do NOT run `npm audit fix --force` or `yarn audit --level critical` blindly.** Major-version bumps in `react-router` or `ai` can break routing/streaming.
- **Do NOT ignore transitive advisories.** The `ai` SDK brings in many packages; audit the full tree.
- **Do NOT commit `node_modules` changes.** Only `package.json` and the chosen lockfile should change.

### Acceptance criteria

- Only one lockfile remains in `frontend/`.
- `npm audit --audit-level=high` (or `yarn audit --level high`) reports zero high/critical vulnerabilities.
- `yarn build` passes.
- All critical user flows (chat, agent run, routing) are manually smoke-tested.

### Verification

- Only one lockfile exists in `frontend/`.
- `npm audit --audit-level=high` (or `yarn audit --level high`) reports zero high/critical vulnerabilities.
- `yarn build` passes.

---

## Plan 020 — Upgrade vulnerable Python dependencies

**Priority:** P1 | **Effort:** M | **Risk:** HIGH | **Category:** security  
**Files in scope:**

- `pyproject.toml`
- `requirements.txt` if present
- Bench environment (rebuild)

### Current state

`pip-audit` found HIGH-severity advisories in `litellm`, `chromadb`, `llama-index-core`, `requests`, `urllib3`, `aiohttp`, `pillow`, and `nltk`. These are reachable through agent HTTP tools, image generation, OCR, and knowledge ingestion.

### Security goal

Pin minimum patched versions so a fresh install does not pull known-vulnerable packages.

### Feature preservation

- LiteLLM-based tool calls, image generation, TTS/STT, and transcription must continue to work.
- Chroma-based knowledge ingestion/retrieval must continue to work.
- OCR (Pillow) and text processing (NLTK) must continue to work.

### Concrete implementation

1. Update `pyproject.toml` with minimum patched versions. Use the latest patched releases known at implementation time:

```toml
dependencies = [
    "openai-agents",
    "litellm>=1.83.11",
    "llama-index-core>=0.13.0",
    "sqlite-vec",
    "pysqlite3-binary; platform_machine == 'x86_64' and python_version < '3.14'",
    "httpx>=0.24.0",
    "chromadb>=0.6.0",
    "llama-index-vector-stores-chroma>=0.4.0",
    "pypdf>=4.0.0",
    "python-docx>=1.1.0",
    "beautifulsoup4>=4.12.0",
    "aiohttp>=3.14.0",
    # Transitive security pins
    "requests>=2.33.0",
    "urllib3>=2.7.0",
    "pillow>=12.2.0",
    "nltk>=3.9.4",
]
```

2. Rebuild the bench environment:

```bash
cd /workspace/development/16
bench setup requirements
bench --site huf.localhost migrate
```

3. Run `pip-audit` again:

```bash
pip-audit --desc
```

4. Run the backend test suite:

```bash
bench --site huf.localhost run-tests --app huf
```

### STOP conditions / pitfalls

- **Do NOT pin exact versions unless necessary.** Minimum bounds allow security patches to flow in.
- **Do NOT bump major versions of `litellm` without checking the changelog.** LiteLLM changes model-name normalization and tool-call formats frequently.
- **Do NOT bump `chromadb` without verifying API compatibility.** Chroma had breaking changes around v0.5→0.6; run knowledge-ingestion smoke tests after upgrading.
- **Do NOT forget transitive pins.** Even if `requests` is not a direct dependency, vulnerable versions can still be resolved unless a lower bound is declared.
- **Do NOT trust the constraint list alone.** Re-run `pip-audit` after install; advisories are point-in-time.

### Acceptance criteria

- `pip-audit --desc` reports no high/critical reachable advisories.
- `bench --site huf.localhost run-tests --app huf` passes.
- A smoke test of an agent run with an image generation or knowledge tool passes.

### Verification

- `pip-audit --desc` reports no high/critical reachable advisories.
- `bench --site huf.localhost run-tests --app huf` passes.

---

## Plan 021 — Remove hardcoded development credentials

**Priority:** P3 | **Effort:** S | **Risk:** LOW | **Category:** security  
**Files in scope:**

- `docker/docker-compose.yml`
- `docker/init.sh`
- `api-docs/bruno/huf_apis/auth/Login.yml`
- `api-docs/bruno/huf_apis/providers/AI Provider Creation.yml`
- `.env.example` (create)

### Current state

Hardcoded default passwords and example API keys are committed:

- `docker/docker-compose.yml:12` `MYSQL_ROOT_PASSWORD: 123`
- `docker/init.sh:8-9` `DB_ROOT_PW=${DB_ROOT_PW:-123}`, `ADMIN_PW=${ADMIN_PW:-admin}`
- `api-docs/bruno/.../Login.yml:14` `"pwd":"admin"`
- `api-docs/bruno/.../AI Provider Creation.yml:14` `"api_key":"2134567934"`

### Security goal

No production-equivalent credentials should be committed to the repository.

### Feature preservation

- Local Docker setup must still work out of the box with documented defaults.
- Bruno collection must still be usable by importing environment variables.

### Concrete implementation

1. Replace hardcoded values with environment-variable references:

```yaml
# docker/docker-compose.yml
environment:
  MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD:-huf_dev_mysql_root}
```

```bash
# docker/init.sh
DB_ROOT_PW=${DB_ROOT_PW:-huf_dev_mysql_root}
ADMIN_PW=${ADMIN_PW:-huf_dev_admin}
```

2. Add a `.env.example` at the repo root:

```bash
# Huf local development defaults
# Copy to .env and change values before using in any non-local environment.
MYSQL_ROOT_PASSWORD=huf_dev_mysql_root
ADMIN_PASSWORD=huf_dev_admin
```

3. Update Bruno files to use collection/environment variables:

```yaml
# api-docs/bruno/huf_apis/auth/Login.yml
body:
  data: |-
    {
      "usr":"Administrator",
      "pwd":"{{ADMIN_PASSWORD}}"
    }
```

```yaml
# api-docs/bruno/huf_apis/providers/AI Provider Creation.yml
body:
  data: |-
    {
      "provider_name":"Demo Provider",
      "api_key":"{{API_KEY}}"
    }
```

Add a note in `api-docs/bruno/README.md` (create the file if it does not exist) explaining how to create a Bruno environment with these variables.

### STOP conditions / pitfalls

- **Do NOT use values like `password123` or `admin` even as defaults.** They end up in credential-stuffing lists.
- **Do NOT remove the default fallbacks entirely.** New developers should still be able to run `docker-compose up` without manual configuration.
- **Do NOT commit a real `.env` file.** Only `.env.example` should be tracked.

### Acceptance criteria

- `grep -R "MYSQL_ROOT_PASSWORD: 123\|DB_ROOT_PW:-123\|ADMIN_PW:-admin\|pwd.*admin\|api_key.*2134567934" docker/ api-docs/` returns no matches.
- `docker-compose up` still works with the new defaults.
- Bruno collection documentation explains variable setup.

### Verification

- `grep -R "MYSQL_ROOT_PASSWORD: 123\|DB_ROOT_PW:-123\|ADMIN_PW:-admin\|pwd.*admin\|api_key.*2134567934" docker/ api-docs/` returns no matches.

---

## Findings from PR #302 still valid / already tracked

These are not duplicated below; keep them on the backlog from `plans/001-007`:

- SSRF guard bypass (IPv6 + redirects) → plans 001–002.
- `flow_webhook` unauthenticated execution → plan 003.
- ElevenLabs webhook fail-open + credential-length leak → plan 004.
- Guest CRUD `reference_doctype` bypass → plan 005.
- SVG artifact `dangerouslySetInnerHTML` → plan 006 (superseded in part by plan 014 above).
- `docs_renderer.py` path traversal → plan 007.

## Rejected/deferred (not worth a plan this round)

- **Guest HTTP proxy surface (`http_handler.py`)** — already mitigated by `validate_url` and `allowed_for_guest`; a broader redesign is out of scope for this round.
- **HTML iframe `allow-scripts`** — tracked in plan 014.
- **Knowledge file upload client-side validation** — defense-in-depth; backend is the authoritative guard.

---

## PR description (proposed)

```markdown
## Security improvement plans — Round 2

This PR adds a second set of security improvement plans based on a fresh `/improve security` audit of the `develop` branch (`acd025f`).

It does **not** change application code — it documents the next set of findings and handoff plans for follow-up implementation PRs.

### What's new since PR #302

- Conversation mutation APIs (`add_message`, `send_message_to_conversation`, `upload_audio_and_transcribe_web`, `set_conversation_data`) need ownership checks.
- `get_result_context` can read arbitrary DocTypes without permission checks.
- `Huf Data Table` management APIs bypass capability checks.
- TTS/STT API keys are written to `os.environ`.
- Frontend artifact rendering (SVG, HTML, JSX, code blocks) has multiple stored-XSS/code-execution sinks.
- Frontend and Python dependency lockfiles contain known HIGH-severity advisories.
- Hardcoded dev credentials remain in Docker and Bruno API docs.

### Files changed

- `doc/security-improvement-plans-2.md`
- `plans/README.md` (index update)

### Suggested review order

Read `doc/security-improvement-plans-2.md`; execute plans in the order listed in the summary table.
```
