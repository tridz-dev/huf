# Backend / System-Agent Findings — Hub Simple

> Read-only recon, branch `feat/design-simplified-hub-homepage-interface` merged with develop.  
> Focus: backend support for the "Hub Orchestrator" agent concept and the chat API path used by the Hub Simple frontend.

---

## B1. Hub Orchestrator Reference

**Search:** `rg -i "hub orchestrator"` returns only frontend surface + prompt files; **zero backend references**.

| File | Line | What it does |
|------|------|--------------|
| `frontend/src/pages/HubSimplePage.tsx` | 133 | Calls `sendMessage({ agent: 'Hub Orchestrator', message: msg, conversationId }, …)` |
| `frontend/src/pages/HubSimplePage.tsx` | 144 | Fallback text shown on any exception: `"Hub Orchestrator agent is not configured yet. Go to Agents to set one up."` |
| `frontend/src/components/hub/HubConversationView.tsx` | 72 | UI label renders `"Hub Orchestrator"` with a `"System"` badge for every assistant message |
| `frontend/src/components/hub/HubConversationView.tsx` | 78-79 | Provider-missing UI: `"No AI Provider configured"` / `"Add a provider and model to start using Hub Orchestrator."` |
| `ongoing/hub-simple-analysis/prompts/02b-backend-agents.txt` | — | Task definition referencing the PR note |
| `ongoing/hub-simple-analysis/STATE.md` | 9 | PR note: "Hub Orchestrator agent needs seeding on install (follow-up); no backend changes" |

**Lookup mechanism:** the agent name `"Hub Orchestrator"` is **hardcoded** as a string literal in `HubSimplePage.tsx:133`. There is no slug, constant, config, or fallback agent lookup.

**Fallback behavior:**
1. If no `AI Provider` exists, `HubSimplePage.tsx:112-116` short-circuits and shows the `__NO_PROVIDER__` placeholder, which `HubConversationView.tsx:76-82` renders as an amber "No AI Provider configured" card with a link to `/huf/models`.
2. If the provider exists but the agent `"Hub Orchestrator"` is missing (or any other error occurs), the `catch` block at `HubSimplePage.tsx:143-144` overwrites the assistant bubble with:  
   `"Hub Orchestrator agent is not configured yet. Go to Agents to set one up."`.
3. No backend seeded agent exists today, so a fresh install will hit fallback #2 as soon as a user sends a message.

---

## B2. System / Reserved Agent Concept

### App seeding framework (already in develop)

The framework lives under `huf/ai/app_seeding/` and is **hooked into installation/migration**.

| File | Key fact |
|------|----------|
| `huf/hooks.py:110-115` | `after_install = "huf.install.after_install"`; `after_app_install` includes `"huf.ai.app_seeding.seeder.on_app_installed"`; `after_migrate = "huf.install.after_migrate"` |
| `huf/install.py:63-77` | `after_install()` calls `seed_all()` (via import) after creating providers/models/tools |
| `huf/install.py:108-142` | `after_migrate()` calls `seed_all()` and logs results |
| `huf/ai/app_seeding/scanner.py:5-30` | `find_seed_dirs()` scans every installed app for a `huf/` seed directory; **explicitly skips the `huf` app itself** (`if app == "huf": continue`) |
| `huf/ai/app_seeding/scanner.py:32-49` | `get_seed_files()` returns flat `.json` files per type folder |
| `huf/ai/app_seeding/seeder.py:24-31` | Load order: `prompts` → `tools` → `knowledge` → `agents` → `triggers` |
| `huf/ai/app_seeding/seeder.py:33-77` | `seed_app()` iterates files, parses JSON (single object or list), calls loader per item |
| `huf/ai/app_seeding/seeder.py:90-100` | `on_app_installed(app_name)` seeds only the newly installed app |
| `huf/ai/app_seeding/seeder.py:102-115` | `seed_all_apps()` whitelisted endpoint restricted by `frappe.only_for("System Manager")` |
| `huf/ai/app_seeding/loaders.py:99-127` | `_upsert_doc()` validates Link references; skips records with missing refs; upserts by key field; stores `source_app` and `source_file` |
| `huf/ai/app_seeding/loaders.py:129-137` | `upsert_agent()` maps `tools` → `agent_tool` and `knowledge` → `agent_knowledge` child tables |

**Existing seed files in the huf app:**

- `huf/huf/agents/demo-assistant.json` — seeds a **disabled** demo `Agent` named `"Demo Assistant"` (`"disabled": 1`).
- `huf/huf/prompts/demo-assistant.json` — seeds an `Agent Prompt` titled `"Demo Assistant Prompt"` (`"is_system": 0`).

Because `scanner.py:13` skips `app == "huf"`, these two files are **not currently seeded by the framework**. `FASTERDOCKER_TECHNIQUES.md:633-635` notes that the skip guard was removed in a prior commit for demo builds, but the current code on this branch still contains the guard.

### Could it seed a Hub Orchestrator as-is?

**Yes, mechanically**, if either:
- the skip guard for the `huf` app is removed, or
- the seed file is placed in another installed app’s `huf/agents/` folder.

The `upsert_agent()` loader already supports the required Agent JSON shape (agent name, provider, model, tools array, knowledge array, etc.).

### Does any "system/reserved/default/seeded agent" concept exist today?

| Concept | Exists? | Evidence |
|---------|---------|----------|
| `is_system` / `reserved` / `protected` field on Agent | **NO** | `huf/huf/doctype/agent/agent.json` has no such field. Only provenance fields are `source_app` and `source_file` (hidden, read-only). |
| "default agent" / "system agent" / "reserved agent" code | **NO** | `rg -i "default agent|system agent|reserved"` over Python backend returns nothing relevant (only IP-address `reserved` checks, `is_system_role` on Huf Role, and design docs). |
| Seeding of agents | **Partially** | Framework exists and runs on `after_install`/`after_migrate`, but the only agent seed file in the repo is `demo-assistant.json` and the `huf` app is skipped by the scanner. |
| `source_app` / `source_file` provenance | **YES** | `agent.json:691-702` — hidden, read-only fields populated by loaders. They are **not** used for protection/locking. |
| `is_system_role` on Huf Role | **YES** | `huf_role.json:34-41` — marks seeded roles, description says "System roles cannot be deleted or renamed" (read-only check field only; no controller enforcement found). |
| `Agent.allow_rename` | **YES** | `agent.json:3` — `"allow_rename": 1`, so any user with write permission can rename an agent. |

**Conclusion:** the codebase has a generic seeding engine and provenance fields, but **no concept of a protected/system/reserved Agent**. A seeded "Hub Orchestrator" would be an ordinary Agent document that users can rename, disable, or delete.

---

## B3. What Seeding a Hub Orchestrator Would Take

### Required fields (from `Agent` doctype JSON + controller)

| Field | Mandatory? | Notes |
|-------|------------|-------|
| `agent_name` | **YES** | Unique, required; would be `"Hub Orchestrator"` to match frontend hardcoding. |
| `provider` | **YES** | Link to `AI Provider`. The provider must exist before seeding or the loader skips with missing refs. |
| `model` | **YES** | Link to `AI Model`. The model must exist before seeding or the loader skips. |
| `instructions` | **YES** (if `prompt_mode == "Local"`) | `agent.py:237-238` validates presence in Local mode. |
| `temperature` | Defaulted to `1` | Non-negative float. |
| `top_p` | Defaulted to `1` | Float. |
| `allow_chat` | **Must be `1`** | Required for streaming; `run_agent_stream()` rejects agents with `allow_chat == 0` at `agent_integration.py:1374-1379`. |
| `persist_conversation` | **Should be `1`** | `agent.py:114-115` forbids `allow_chat == 1 && persist_conversation == 0`. |
| `disabled` | Should be `0` | Otherwise the agent cannot run. |
| `max_turns` | Defaulted to `20` | Safety limit. |
| `history_limit` | Defaulted to `20` | For context strategy. |
| `context_strategy` | Defaulted to `"Summarize"` | |

### Dependencies that must pre-exist

1. **AI Provider** with a valid `provider_name`, `provider_brand`, and `api_key`. `install.py:161-191` seeds many demo providers with empty API keys (using `ignore_mandatory` / `ignore_validate`), but an agent cannot actually run until an API key is set — `AgentManager._setup_client()` throws `"API key is not configured"` (`agent_integration.py:96-97`).
2. **AI Model** linked to that provider. `install.py:193-275` seeds demo models.
3. **Agent Tool Type** documents if the orchestrator is given tools. `loaders.upsert_tool()` auto-creates missing tool types.

### Recommended tools / permissions for a useful orchestrator

To make the hub agent useful (navigate users, answer about agents/runs), it would need tools such as:

- `search_documents` / `get_list` on `Agent` — list active agents.
- `get_document` on `Agent` — describe a specific agent.
- `get_list` on `Agent Run` / `Agent Conversation` — show recent runs.
- `get_document` on `Agent Run` — run details.
- Possibly `run_flow` / flow tools if the orchestrator should trigger workflows.
- Possibly integration tools (Slack, Gmail) depending on desired hub behavior.

These would be declared in the seed JSON as `tools: ["tool_name", …]` and mapped to `agent_tool` rows by `loaders.upsert_agent()`.

### Deletion / rename protection concerns

- **No protection today.** `Agent.allow_rename = 1` and there is no `is_system`/`protected` field.
- If a user renames "Hub Orchestrator", the frontend hardcoded lookup at `HubSimplePage.tsx:133` will fail and show the fallback message.
- If a user deletes or disables the agent, the hub chat breaks with the same fallback.
- To make it robust, the backend would need either:
  1. A new `is_system`/`protected` field on Agent with controller hooks preventing delete/rename, **or**
  2. A slug-based lookup (e.g., `hub_orchestrator` identifier stored separately from display name) so the display name can change safely.

---

## B4. Chat API Path

### Hub Simple frontend call chain

| Step | File | Method / Line | Details |
|------|------|---------------|---------|
| 1 | `frontend/src/pages/HubSimplePage.tsx:132-134` | `sendMessage({ agent: 'Hub Orchestrator', message: msg, conversationId }, { useStreaming: streamingAvailable, onDelta })` | Decides streaming vs REST based on global `streamingAvailable` flag. |
| 2a (stream) | `frontend/src/services/streamChatApi.ts:171-263` | `sendMessage()` → `streamAgentResponse()` | Builds SSE request. |
| 2b (REST) | `frontend/src/services/streamChatApi.ts:252-262` | `sendMessage()` → `sendMessageToConversation()` or `newConversation()` | Falls back to REST when streaming unavailable. |
| 3 (SSE) | `frontend/src/services/streamChatApi.ts:84-157` | `streamAgentResponse()` | POST to `/huf/stream/{agentName}` with `{prompt, channel_id: 'Chat', create_new: true \| conversation_id, files?}`. |
| 4 (REST new) | `frontend/src/services/chatApi.ts:512-524` | `newConversation()` | POST `huf.ai.agent_chat.new_conversation` with `{agent, message}`. |
| 5 (REST existing) | `frontend/src/services/chatApi.ts:529-541` | `sendMessageToConversation()` | POST `huf.ai.agent_chat.send_message_to_conversation` with `{conversation, message}`. |

### Backend whitelisted methods

| Whitelisted method | File | Line | Decorator | Notes |
|--------------------|------|------|-----------|-------|
| `run_agent_sync()` | `huf/ai/agent_integration.py` | 631 | `@frappe.whitelist(allow_guest=True)` | Main sync agent runner; guest allowed only if `agent_doc.allow_guest == 1`. |
| `run_agent_stream()` | `huf/ai/agent_integration.py` | 1304 | **Not directly whitelisted** | Called internally by the page renderer and other code. |
| `new_conversation()` | `huf/ai/agent_chat.py` | 370 | `@frappe.whitelist()` | Creates conversation then calls `run_agent_sync()`. |
| `send_message_to_conversation()` | `huf/ai/agent_chat.py` | 408 | `@frappe.whitelist()` | Looks up conversation agent and calls `run_agent_sync()`. |
| `seed_all_apps()` | `huf/ai/app_seeding/seeder.py` | 102 | `@frappe.whitelist()` + `frappe.only_for("System Manager")` | Manual re-seed from UI. |

### SSE endpoint

- **Route registration:** `huf/hooks.py:62-65` and `huf/hooks.py:77-80`:
  - `website_route_rules` maps `/huf/stream/<path:agent_name>` → `huf/stream`.
  - `page_renderer = ["huf.ai.agent_stream_renderer.AgentStreamRenderer"]`.
- **Renderer:** `huf/ai/agent_stream_renderer.py:19-241`.
  - `can_render()` matches paths starting with `huf/stream`.
  - `render()` extracts `agent_name`, reads POST body, then calls `run_agent_stream()`.
  - `channel_id` defaults to `"sse_stream"` (`agent_stream_renderer.py:140`), but the frontend explicitly sends `"Chat"` (`streamChatApi.ts:92`).
  - `external_id` defaults to `frappe.session.user` (`agent_stream_renderer.py:141`).

### Conversation creation semantics

- **Per hub chat session:** In the streaming path, `streamAgentResponse()` sends `create_new: true` when no `conversationId` exists (`streamChatApi.ts:96-98`). The backend `run_agent_stream()` at `agent_integration.py:1387-1390` creates a new `Agent Conversation` titled `"Streaming chat with {agent_name}"`.
- **Owner:** `create_new_conversation()` in `conversation_manager.py:336-352` inserts with `ignore_permissions=True`; the doc owner becomes the current Frappe user via standard insert semantics.
- **Channel:** set to `"Chat"` from the frontend (SSE) or `"Chat"` from `new_conversation()` (`agent_chat.py:379`). The `Agent Conversation` doctype stores `channel` and `external_id`.
- **Session ID:** `ConversationManager.__init__()` at `conversation_manager.py:325-334` builds `session_id = f"{channel}:{external_id}"` when both are present; otherwise `f"{channel}:{frappe.session.user}"`. For the hub this becomes `"Chat:<username>"`.
- **Persistence across reloads:** `HubSimplePage.tsx` keeps `conversationId` in component state only. A page reload starts a **new** conversation unless the previous `conversationId` is recovered from somewhere (it is not stored in URL or localStorage in the current code).
- **Resume:** the same session logic could resume an existing active conversation because `get_or_create_conversation()` filters by `agent`, `session_id`, and `is_active: 1` (`conversation_manager.py:365-374`), but the frontend currently always passes `create_new: true` on first message, so it does not resume.

---

## B5. Permissions

### Who can call the chat endpoints?

#### Frappe role requirements

The chat endpoints are whitelisted but rely on Frappe’s session/auth. There is **no explicit `frappe.only_for(...)`** on the chat methods. The effective gate is:

1. User must be logged in (unless the agent has `allow_guest = 1`).
2. Agent-level access check in `run_agent_sync()` / `run_agent_stream()` via `_is_user_allowed()` (`agent_integration.py:291-315`):
   - Guest allowed only if `agent_doc.allow_guest == 1`.
   - If `allowed_users` is set, user must be in the list.
   - If `allowed_roles` is set, user must have one of the roles.
   - If neither list is set, **any logged-in user** can run the agent.

#### DocType-level permissions

| DocType | System Manager | Huf Manager | Huf User | Huf Viewer |
|---------|----------------|-------------|----------|------------|
| Agent | CRUD | CRUD | Read only | Read only (`agent.json:752-799`) |
| AI Provider | CRUD | Read/select | Read | (none listed) (`ai_provider.json:68-106`) |
| AI Model | CRUD | Read | Read | (none listed) (`ai_model.json:90-128`) |
| Agent Conversation | CRUD | CRUD | Create/Read/Write | Read only (`agent_conversation.json:201-250`) |
| Agent Message | CRUD | CRUD | Create/Read/Write | Read only |
| Agent Run | CRUD | CRUD | Create/Read/Write | Read only |

#### Capability-level permissions (from `huf/permissions.py`)

- `chat.use` is required for chat functionality in the capability layer.
- `Huf Viewer` capabilities: `agent.use`, `chat.view_own` only (`permissions.py:96-99`).
- `Huf User` capabilities: adds `chat.use`, `knowledge.use`, `tools.use`, `flows.use`.
- `Huf Manager` / `Huf Admin` have broader capabilities.

### Can a "viewer"-type Frappe user chat via the hub?

**It depends on which layer is enforced:**

- **Agent-level `_is_user_allowed()`:** If the Hub Orchestrator agent has no `allowed_users`/`allowed_roles` restrictions, any logged-in user can invoke it, including a Huf Viewer. So the **backend would permit** the chat call.
- **Capability layer / frontend:** `HubSimplePage.tsx:71-73` derives `role` from capabilities. A viewer gets `role = 'viewer'` but the page itself is still rendered. There is no `chat.use` check before sending.
- **DocType permissions:** `Huf Viewer` has read-only on `Agent Conversation`, `Agent Message`, and `Agent Run`. The chat endpoints insert `Agent Message` and `Agent Run` docs with `ignore_permissions=True` internally, so read-only DocType permissions do **not** block chat creation.

**Verdict:** A Huf Viewer user can currently chat via the hub if the agent is unrestricted. If the intended product behavior is viewer = read-only, the frontend or backend should enforce `chat.use` (or `agent.use` + ownership) before invoking the agent.

### Guest access concerns for `/`

- The `/` route is wrapped in `<ProtectedRoute>` (`App.tsx:80-88`).
- `ProtectedRoute.tsx:10-20` waits for `isAuthenticated` from `UserContext`; unauthenticated users get redirected (handled by `UserContext`) and render `null`.
- Therefore the **React frontend does not render `/` for guests**.
- However, the underlying SSE endpoint `/huf/stream/<agent_name>` is a Frappe page renderer, not a `@frappe.whitelist()` method. It inherits Frappe’s standard website/session authentication. The `run_agent_stream()` function inside it checks `agent_doc.allow_guest`: if the Hub Orchestrator agent had `allow_guest = 1`, a guest with a valid session cookie could theoretically hit the SSE endpoint directly. In practice the frontend blocks guests from reaching it.
- There is no `@frappe.whitelist(allow_guest=True)` on `new_conversation()` or `send_message_to_conversation()`, so the REST fallback is **not guest-accessible**.

---

## Summary / Verdict

- **B1:** Hub Orchestrator is hardcoded by display name; fallback is a generic "not configured" message.
- **B2:** Seeding framework exists and runs on install/migrate, but the `huf` app is skipped and there is no system/reserved agent concept.
- **B3:** Seeding a Hub Orchestrator is straightforward mechanically, but it would be a normal deletable/renamable Agent; robust seeding needs a protected/slug-based design.
- **B4:** Chat uses `/huf/stream/{agent}` (SSE) with fallback to `new_conversation`/`send_message_to_conversation`; conversations are created per hub chat session with owner = current user, channel = `Chat`, session_id = `Chat:<username>`.
- **B5:** Chat endpoints are not restricted by Frappe role or capability; any logged-in user can invoke an unrestricted agent. Guests are blocked by the frontend route guard, but the SSE endpoint’s guest behavior depends on the agent’s `allow_guest` flag.

<verdict: MIXED>
