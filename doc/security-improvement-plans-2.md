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

- `huf/ai/agent_chat.py` (`send_message_to_conversation`, `upload_audio_and_transcribe_web`, `add_message`)
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

### Steps

1. Add a shared helper `_assert_conversation_access(conversation)` that verifies:
   - `frappe.session.user` is the conversation `owner`, **or**
   - the conversation `session_id` matches the caller's session/channel.
2. Call the helper at the start of `send_message_to_conversation`, `upload_audio_and_transcribe_web`, `add_message`, and `handle_set_conversation_data`.
3. Where `ignore_permissions=True` is used inside `ConversationManager.add_message`, ensure it is gated by the ownership check at the API layer.
4. Add tests covering:
   - owner can mutate their own conversation;
   - other authenticated user cannot;
   - guest cannot mutate an authenticated user's conversation.

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

No permission check restricts the DocType or document.

### Steps

1. Maintain an explicit allow-list of doctypes that may be returned (e.g. `Agent Tool Call`, `Agent Context Artifact`).
2. For allow-listed doctypes, assert `frappe.has_permission(reference_doctype, "read", doc=reference_name)`.
3. Return a permission error for any other doctype; do not fall back to `doc.as_dict()`.
4. Add regression tests for allow-listed and blocked doctypes.

### Verification

- New tests pass.
- Attempting to fetch `User`/`AI Provider` via the tool returns a permission error.

---

## Plan 010 — Add capability checks to Huf Data Table management APIs

**Priority:** P1 | **Effort:** S | **Risk:** MED | **Category:** security  
**Files in scope:**

- `huf/huf/doctype/huf_data_table/api.py`
- `huf/permissions.py` (add capability if needed)

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

No Huf capability check is performed before mutating custom DocTypes.

### Steps

1. Require a capability such as `data_tables.manage` (or reuse `flows.manage` if appropriate) via `huf.permissions.has_capability`.
2. Gate `create_data_table`, `update_data_table`, and `delete_data_table` with this check.
3. Add tests for authorized and unauthorized callers.

### Verification

- Tests pass.
- Calling endpoint as a non-authorized user returns 403 / permission error.

---

## Plan 011 — Enforce file permission checks in `transcribe_audio`

**Priority:** P2 | **Effort:** S | **Risk:** LOW | **Category:** security  
**Files in scope:**

- `huf/ai/sdk_tools.py` (`handle_transcribe_audio`)

### Current state

`handle_transcribe_audio` accepts `file_id`/`file_url` and opens the file without checking `File` read permission or attachment ownership.

### Steps

1. If `file_id` is provided, load the `File` doc and assert `frappe.has_permission("File", "read", doc=file_id)`.
2. Verify the file is attached to an `Agent Message`/`Agent Run` the caller can access, or is owned by the caller.
3. Reject `file_url` inputs that point outside the Frappe file store.

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

### Steps

1. Pass the key directly in `speech_params`/`transcription_params` instead of using `os.environ`.
2. If an environment variable is unavoidable, set it immediately before the call and unset it in a `finally` block.

### Verification

- TTS/STT tests still pass.
- No `os.environ[...] = api_key` patterns remain in `huf/ai/sdk_tools.py`.

---

## Plan 013 — Add per-document permission check in `delete_documents`

**Priority:** P2 | **Effort:** S | **Risk:** LOW | **Category:** security  
**Files in scope:**

- `huf/ai/tool_functions.py` (`delete_documents`)

### Current state

```python
# huf/ai/tool_functions.py:193-199
def delete_documents(doctype: str, document_ids: list):
    for document_id in document_ids:
        frappe.delete_doc(doctype, document_id)
```

No per-document delete permission check.

### Steps

1. Inside the loop, mirror `handle_delete_document`: check `frappe.has_permission(doctype, "delete", doc=document_id)` and skip/report failures.
2. Add a regression test.

### Verification

- Test for unauthorized bulk delete fails before fix and passes after.

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

### Steps

1. Render SVG inside a sandboxed `<iframe srcDoc={svg} sandbox="" />` instead of `dangerouslySetInnerHTML`.
2. Default the HTML iframe sandbox to empty (`sandbox=""`). Only enable `allow-scripts` when the artifact type explicitly requires interactivity.
3. Optionally sanitize SVG with DOMPurify's SVG profile as defense-in-depth.

### Verification

- `yarn typecheck` and `yarn build` pass.
- Existing artifact rendering tests (if any) pass; add a test that asserts no `dangerouslySetInnerHTML` for SVG.

---

## Plan 015 — Sandbox JSX previews to prevent arbitrary JS execution

**Priority:** P1 | **Effort:** M | **Risk:** HIGH | **Category:** security  
**Files in scope:**

- `frontend/src/components/ui/jsx-preview.tsx`

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

### Steps

1. **Primary fix:** render JSX previews in a sandboxed iframe with `sandbox="allow-scripts"` (no `allow-same-origin`) so scripts cannot access parent origin cookies/localStorage.
2. **Defense-in-depth:** remove dangerous bindings (`Object`, `Array`, `console`) from `defaultBindings`.
3. Add `blacklistedAttrs={[/^on[A-Z]/i]}` to block event handlers.
4. Add regression tests that assert malicious JSX payloads cannot access `window.parent` or exfiltrate cookies.

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

### Steps

1. Pass the highlighted HTML through DOMPurify before assignment.
2. Escape the fallback `code` path instead of injecting it raw.
3. Add a regression test that asserts the fallback path is escaped.

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

### Steps

1. Replace with pure string replacement for the five entities (`&lt;`, `&gt;`, `&quot;`, `&#39;`, `&amp;`).
2. Apply the same change in `PreviewViewPage.tsx`.
3. Add unit tests for entity decoding.

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

### Steps

1. Validate `returnTo` against an allow-list of internal paths or reject absolute/protocol-relative URLs.
2. Strip `javascript:` and `data:` schemes.
3. Add a regression test.

### Verification

- `yarn typecheck` passes.
- Malicious `returnTo` values are rejected.

---

## Plan 019 — Upgrade vulnerable frontend lockfile dependencies

**Priority:** P1 | **Effort:** S/M | **Risk:** HIGH | **Category:** security  
**Files in scope:**

- `frontend/package-lock.json`
- `frontend/package.json` (constraints if needed)

### Current state

`npm audit --audit-level=high` reports HIGH-severity advisories including `react-router` and `ai` SDK transitive packages. `package.json` pins `react-router-dom@^7.9.4` and `ai@^6.0.116`, but the lockfile resolves older/vulnerable versions.

### Steps

1. Regenerate `package-lock.json` from `package.json` (`rm package-lock.json && npm install`).
2. Run `npm audit fix` for any remaining high/critical advisories.
3. Verify routing in `App.tsx` and the build still work.
4. Add `npm audit --audit-level=high` to CI if not present.

### Verification

- `npm audit --audit-level=high` reports zero high/critical vulnerabilities.
- `yarn build` passes.

---

## Plan 020 — Upgrade vulnerable Python dependencies

**Priority:** P1 | **Effort:** M | **Risk:** HIGH | **Category:** security  
**Files in scope:**

- `pyproject.toml`
- `requirements.txt` if present

### Current state

`pip-audit` found HIGH-severity advisories in `litellm`, `chromadb`, `llama-index-core`, `requests`, `urllib3`, `aiohttp`, `pillow`, and `nltk`. These are reachable through agent HTTP tools, image generation, OCR, and knowledge ingestion.

### Steps

1. Pin minimum patched versions in `pyproject.toml`:
   - `litellm>=1.83.11`
   - `chromadb>=...` (latest patched)
   - `llama-index-core>=0.13.0`
   - Add/refresh lower bounds for transitive deps (`requests>=2.33.0`, `urllib3>=2.7.0`, `aiohttp>=3.14.0`, `pillow>=12.2.0`, `nltk>=3.9.4`).
2. Rebuild the bench environment and run `pip-audit` again.
3. Run the backend test suite.

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

### Current state

Hardcoded default passwords and example API keys are committed:

- `docker/docker-compose.yml:12` `MYSQL_ROOT_PASSWORD: 123`
- `docker/init.sh:8-9` `DB_ROOT_PW=${DB_ROOT_PW:-123}`, `ADMIN_PW=${ADMIN_PW:-admin}`
- `api-docs/bruno/.../Login.yml:14` `"pwd":"admin"`
- `api-docs/bruno/.../AI Provider Creation.yml:14` `"api_key":"2134567934"`

### Steps

1. Replace hardcoded values with environment-variable references (e.g. `${MYSQL_ROOT_PASSWORD}`, `${ADMIN_PASSWORD}`).
2. Add a `.env.example` documenting required variables.
3. Replace Bruno example credentials with placeholders like `{{ADMIN_PASSWORD}}` / `{{API_KEY}}`.

### Verification

- `grep -R "MYSQL_ROOT_PASSWORD: 123\|ADMIN_PW:-admin\|pwd.*admin\|api_key.*2134567934" docker/ api-docs/` returns no matches.

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
