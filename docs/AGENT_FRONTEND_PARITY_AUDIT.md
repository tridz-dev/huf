# HUF Agent DocType — Frontend Parity Audit

**Date:** 2026-03-19  
**Scope:** Full implementation gap analysis between Agent DocType (backend) and React frontend  
**Branch:** dev/huf-agent-frontend-parity-e251

---

## 1. Overview

### What Was Analyzed

- **Backend:** `huf/huf/doctype/agent/agent.json`, `agent.py`, and related modules (`agent_integration.py`, `prompt_resolver.py`, `knowledge/`, `providers/litellm.py`, etc.)
- **Frontend:** `frontend/src/pages/AgentFormPage.tsx`, `frontend/src/components/agent/*`, `frontend/src/services/agentApi.ts`, `frontend/src/types/agent.types.ts`

### Summary of Findings

| Category | Count |
|----------|-------|
| **Complete** (fully implemented) | 28 fields |
| **Partial** (UI exists but issues) | 5 fields |
| **Missing** (no UI) | 12 fields |
| **Misaligned** (field name / behavior mismatch) | 2 fields |

**Critical gaps:** Knowledge tab, Permissions tab, Metadata tab, Prompt Template mode UI, and field name mismatch for `template_version_at_attach`.

---

## 2. Field Mapping Table

| Field | Backend | Frontend | Status |
|-------|---------|----------|--------|
| `agent_name` | yes | yes | complete |
| `provider` | yes | yes | complete |
| `model` | yes | yes | complete |
| `temperature` | yes | yes | complete |
| `top_p` | yes | yes | complete |
| `description` | yes | yes | complete |
| `instructions` | yes | yes | complete |
| `disabled` | yes | yes | complete |
| `allow_chat` | yes | yes | complete |
| `persist_conversation` | yes | yes | complete |
| `persist_user_history` | yes | yes | complete |
| `enable_multi_run` | yes | yes | complete |
| `default_plan` | yes | yes | complete |
| `agent_tool` | yes | yes | complete |
| `agent_mcp_server` | yes | yes | complete |
| `prompt_mode` | yes | partial | partial — Local only; Template mode UI missing |
| `agent_prompt` | yes | partial | partial — in schema, no Template UI |
| `prompt_version_locked` | yes | partial | partial — in schema, no Template UI |
| `template_version_at_attach` | yes | misaligned | misaligned — frontend uses `attached_at_version` |
| `copied_from_prompt` | yes | no | missing (hidden, read-only) |
| `enable_prompt_caching` | yes | yes | complete |
| `cache_control_type` | yes | yes | complete |
| `cache_system_message` | yes | yes | complete |
| `cache_conversation_history` | yes | yes | complete |
| `context_strategy` | yes | yes | complete |
| `summary_ratio` | yes | yes | complete |
| `history_limit` | yes | yes | complete |
| `summary_model` | yes | no | missing |
| `max_knowledge_tokens` | yes | yes | complete |
| `max_turns` | yes | yes | complete |
| `enable_conversation_data` | yes | yes | complete |
| `autonaming_of_conversation_title` | yes | yes | complete |
| `image_generation_model` | yes | yes | complete |
| `tts_model` | yes | yes | complete |
| `tts_voice` | yes | yes | complete |
| `stt_model` | yes | yes | complete |
| `agent_color` | yes | partial | partial — used in chat, not editable in form |
| `allow_guest` | yes | no | missing |
| `allowed_users` | yes | no | missing |
| `allowed_roles` | yes | no | missing |
| `agent_knowledge` | yes | no | missing |
| `last_run` | yes | partial | partial — shown on list, not in form |
| `total_run` | yes | partial | partial — shown on list, not in form |
| `chef` | yes | no | hidden, fetch_from |
| `slug` | yes | no | hidden, fetch_from |
| `async` | yes | no | hidden |

---

## 3. Missing / Partial Features — Detailed Section

### Field: `agent_knowledge`

#### 1. Purpose
Child table linking Knowledge Sources to the agent. Each row defines: `knowledge_source` (Link), `mode` (Mandatory/Optional), `priority`, `max_chunks`, `token_budget`, `description`.

#### 2. Backend Behavior
- **`huf/ai/knowledge/tool.py`:** `create_knowledge_search_tool`, `create_get_knowledge_sources_tool` — only if `agent.agent_knowledge` has entries.
- **`huf/ai/knowledge/context_builder.py`:** `build_knowledge_context` uses `get_mandatory_knowledge(agent_name)` which reads `agent_knowledge` for Mandatory sources.
- **`huf/ai/knowledge/retriever.py`:** `knowledge_search` filters by `agent_knowledge` for allowed sources.
- **`huf/ai/agent_integration.py`:** Injects knowledge context before execution when Mandatory sources exist.

#### 3. Current Frontend Status
**Missing.** No Knowledge tab, no `agent_knowledge` UI. Form has no `agent_knowledge` in payload.

#### 4. Required UI Implementation
- **Tab:** Add "Knowledge" tab (backend has `knowledge_tab`).
- **Section:** "Knowledge Sources" with editable grid.
- **Columns:** Knowledge Source (Link), Mode (Select: Mandatory/Optional), Priority (Int), Max Chunks (Int), Token Budget (Int), Description (Small Text).
- **Actions:** Add row, remove row, reorder.
- **Dependencies:** Fetch Knowledge Source list via `db.getDocList('Knowledge Source', { fields: ['name', 'source_name', 'status'], filters: [['status', '=', 'Ready']] })`.

#### 5. Data Flow
- **Load:** `getAgent` returns `agent_knowledge` as child table. Map to form state.
- **Save:** Include `agent_knowledge` in `agentData` when calling `updateAgent`/`createAgent`. Format: `[{ knowledge_source, mode, priority, max_chunks, token_budget, description }]`.

#### 6. API / Method Dependencies
- `db.getDoc('Agent', name)` — includes child tables.
- `db.createDoc` / `db.updateDoc` — accept child table arrays.

#### 7. Related Doctypes
- **Knowledge Source** (Link) — list available sources.
- **Agent Knowledge** (child table).

#### 8. Example Usage
```json
{
  "agent_knowledge": [
    { "knowledge_source": "Product-Docs", "mode": "Mandatory", "priority": 1, "max_chunks": 5, "token_budget": 2000 },
    { "knowledge_source": "FAQ", "mode": "Optional", "priority": 0, "max_chunks": 3, "token_budget": 1000 }
  ]
}
```

#### 9. Edge Cases
- Empty `agent_knowledge` → no knowledge tools, no context injection.
- Mandatory source with status != Ready → may fail at runtime.
- Validate `max_chunks` and `token_budget` >= 0.

---

### Field: `prompt_mode` / `agent_prompt` / `prompt_version_locked` / `template_version_at_attach`

#### 1. Purpose
- **prompt_mode:** `Local` (inline instructions) or `Template` (link to Agent Prompt).
- **agent_prompt:** Link to Agent Prompt when mode is Template.
- **prompt_version_locked:** If set, agent uses the version at attach time.
- **template_version_at_attach:** Read-only version number when prompt was attached.

#### 2. Backend Behavior
- **`huf/ai/prompt_resolver.py`:** `resolve_prompt(agent_doc)` — Local returns `instructions`; Template loads from Agent Prompt, optionally locked to `template_version_at_attach`.
- **`huf/huf/doctype/agent/agent.py`:** `_validate_prompt()` — Template mode requires `agent_prompt`; `_record_template_version()` sets `template_version_at_attach` on attach/change.

#### 3. Current Frontend Status
- **Partial:** `prompt_mode` in schema; GeneralTab only shows Instructions when `prompt_mode === "Local"`.
- **Missing:** No Template mode UI — no `agent_prompt` selector, no `prompt_version_locked` toggle.
- **Misaligned:** Frontend uses `attached_at_version` but backend field is `template_version_at_attach`. Load/save never map correctly.

#### 4. Required UI Implementation
- **GeneralTab:** Add Prompt Mode selector (Local / Template).
- **When Template:** Show Agent Prompt combobox (fetch from `db.getDocList('Agent Prompt', { fields: ['name', 'title', 'version', 'is_latest'], filters: [['is_active', '=', 1]] })`), Lock Version checkbox, read-only "Attached at Version".
- **Data mapping:** Use `template_version_at_attach` in payload; map `data.template_version_at_attach` → form `attached_at_version` for display only.

#### 5. Data Flow
- **Load:** `data.prompt_mode`, `data.agent_prompt`, `data.prompt_version_locked`, `data.template_version_at_attach` (map to form).
- **Save:** Send `template_version_at_attach` (not `attached_at_version`). Backend sets it on attach; frontend should not overwrite unless detaching.

#### 6. API / Method Dependencies
- `huf.ai.prompt_api.attach_prompt_to_agent` — optional; can use direct doc update.
- `db.getDocList('Agent Prompt', ...)` for prompt picker.

#### 7. Related Doctypes
- **Agent Prompt** (Link).

#### 8. Edge Cases
- Switching Template → Local: clear `agent_prompt`, `prompt_version_locked`, `template_version_at_attach`.
- Switching Local → Template: require `agent_prompt` before save.
- Locked template: backend resolves via `_get_locked_version_body`; UI should show "Locked to vX".

---

### Field: `summary_model`

#### 1. Purpose
Optional lightweight model for summarization when `context_strategy === "Summarize"` and history exceeds `history_limit`.

#### 2. Backend Behavior
- **`huf/ai/agent_integration.py`:** `run_background_summarization` — uses `agent_doc.summary_model or agent_doc.model`; if `summary_model` set, uses its provider for API key.

#### 3. Current Frontend Status
**Missing.** Not in form schema or AdvancedTab.

#### 4. Required UI Implementation
- **AdvancedTab → Context Settings:** Add "Summary Model" (Link to AI Model), optional. Filter models by provider (or all models). Description: "Optional: Lightweight model for summarization tasks."

#### 5. Data Flow
- Load/save like other model links. Include in `agentData.summary_model`.

#### 6. API / Method Dependencies
- Same as `tts_model` / `stt_model` — no modality filter; any text model is valid.

#### 7. Related Doctypes
- **AI Model** (Link).

---

### Field: `allow_guest` / `allowed_users` / `allowed_roles`

#### 1. Purpose
- **allow_guest:** If set, Guest users can run the agent via API.
- **allowed_users:** Table MultiSelect — if non-empty, only listed users can access.
- **allowed_roles:** Table MultiSelect — if non-empty, only users with listed roles can access.
- **Logic (agent.py `get_permission_query_conditions`, `has_permission`):** If both tables empty → public. Otherwise: owner OR in allowed_users OR has role in allowed_roles.

#### 2. Backend Behavior
- **`huf/ai/agent_integration.py`:** `run_agent_sync` checks `agent_doc.allow_guest` for Guest; `has_permission` used for doc access.

#### 3. Current Frontend Status
**Missing.** No Permissions tab. Backend has `permissions_tab` with `allow_guest`, `allowed_users`, `allowed_roles`.

#### 4. Required UI Implementation
- **Tab:** Add "Permissions" tab.
- **Section:** "Access Control"
- **Fields:** Allow Guest (Switch), Allowed Users (multi-select from User), Allowed Roles (multi-select from Role).
- **UX:** Explain "If both lists empty, anyone can access. Otherwise only owner, listed users, or users with listed roles."

#### 5. Data Flow
- **Load:** `data.allow_guest`, `data.allowed_users` (array of `{ user }`), `data.allowed_roles` (array of `{ role }`).
- **Save:** `agentData.allow_guest`, `agentData.allowed_users`, `agentData.allowed_roles` in Frappe child table format.

#### 6. API / Method Dependencies
- `db.getDocList('User', { fields: ['name'] })` for user picker.
- `db.getDocList('Role', { fields: ['name'] })` for role picker.

#### 7. Related Doctypes
- **Agent User** (child), **Agent Role** (child), **User**, **Role**.

---

### Field: `agent_color`

#### 1. Purpose
Hex color for agent avatar in chat (e.g. `#6366F1`).

#### 2. Backend Behavior
- **`agent.py`:** `set_default_color()` — assigns random color on insert if empty.
- **Chat:** Used in `ChatAvatar`, `ChatListing`, `ChatWindowHeader`, `EmptyChatState`.

#### 3. Current Frontend Status
**Partial.** Color is used in chat UI and loaded for list/detail, but there is no editable field in the Agent form.

#### 4. Required UI Implementation
- **AdvancedTab → Huf UI section:** Add "Agent Color" (Input with color picker or hex input). Placeholder: `#6366F1`. Description: "Background color for agent avatar in chat."

#### 5. Data Flow
- Include in form schema, load from `data.agent_color`, save in `agentData.agent_color`.

---

### Field: `last_run` / `total_run`

#### 1. Purpose
Read-only metadata: last execution timestamp and total run count.

#### 2. Backend Behavior
- Updated by `agent_integration.py` on each run.
- Used for list display and metrics.

#### 3. Current Frontend Status
**Partial.** Shown on AgentsPage (list) and in ItemCard metadata. Not shown in Agent form.

#### 4. Required UI Implementation
- **Metadata tab (or footer):** Add read-only "Last Run" and "Total Run" when editing existing agent. Use existing `formatTimeAgo` for last_run.

---

### Field: `template_version_at_attach` (misaligned as `attached_at_version`)

#### 1. Purpose
Read-only version of the Agent Prompt when it was attached. Used for version-locked resolution.

#### 2. Backend Behavior
- Set by `agent._record_template_version()` when `agent_prompt` changes.
- Read by `prompt_resolver._get_locked_version_body()`.

#### 3. Current Frontend Status
**Misaligned.** Frontend uses `attached_at_version` everywhere. Backend field is `template_version_at_attach`. Result: value is never loaded or saved correctly.

#### 4. Required UI Implementation
- **Fix mapping:** In load: `data.template_version_at_attach` → form. In save: send `template_version_at_attach` (or keep form key as `attached_at_version` but map to `template_version_at_attach` in payload).
- **Tab config:** Update `tabConfig.general.fields` to reference correct backend field when fetching.

---

### Field: `copied_from_prompt`

#### 1. Purpose
Hidden, read-only. Tracks original prompt when agent was detached from a template (traceability).

#### 2. Backend Behavior
- Set by `prompt_api` when detaching. Not user-editable.

#### 3. Current Frontend Status
**Missing.** Not needed in form; backend manages it. Optional: show in Metadata if we add a Metadata section.

---

## 4. Dependency Graph

```
prompt_mode = "Template"
  ├── agent_prompt (required)
  ├── prompt_version_locked (optional)
  └── template_version_at_attach (read-only, set by backend)

enable_prompt_caching = true
  ├── cache_control_type
  ├── cache_system_message
  └── cache_conversation_history

enable_multi_run = true
  └── default_plan (table)

context_strategy = "Summarize"
  └── summary_model (optional, for summarization)
  └── summary_ratio (optional, currently unused in backend)
```

**Conditional visibility:**
- `prompt_mode === "Local"` → show `instructions`; hide Template fields.
- `prompt_mode === "Template"` → show `agent_prompt`, `prompt_version_locked`, `template_version_at_attach`; hide `instructions`.
- `enable_prompt_caching` → show cache sub-fields.
- `enable_multi_run` → show Default Plan section.

---

## 5. Runtime Impact Summary

| Missing Field | Runtime Impact |
|---------------|----------------|
| `agent_knowledge` | RAG disabled. No knowledge_search tool, no mandatory context injection. |
| `prompt_mode` (Template) | Cannot use Agent Prompt library; only inline instructions. |
| `template_version_at_attach` | Version locking broken; load/save never works. |
| `summary_model` | Summarization uses main model; may be costlier/slower. |
| `allow_guest` | Guest API access cannot be enabled from UI. |
| `allowed_users` / `allowed_roles` | Fine-grained access control not configurable from UI. |
| `agent_color` | Users cannot customize avatar color; relies on backend default. |

---

## 6. Implementation Plan

### P0 (Critical)

1. **Fix `template_version_at_attach` mapping** — Correct load/save to use backend field name.
2. **Add Knowledge tab** — Full `agent_knowledge` CRUD so RAG works from UI.
3. **Add Prompt Template mode** — `agent_prompt` selector, `prompt_version_locked`, proper Template UI in GeneralTab.

### P1 (Important)

4. **Add Permissions tab** — `allow_guest`, `allowed_users`, `allowed_roles`.
5. **Add `summary_model`** — In AdvancedTab Context Settings.
6. **Add `agent_color`** — In AdvancedTab Huf UI section.

### P2 (Nice-to-have)

7. **Add Metadata section** — `last_run`, `total_run` (read-only) in form.
8. **Modality filter fix** — `modelSupports` in AdvancedTab: backend uses `modalities.split(",")` (multi-value); frontend uses exact match. Use `(model.modalities || '').split(',').map(m => m.trim()).includes(required)`.
9. **Cacheable models API** — Optional: call `get_cacheable_models` when prompt caching enabled to show supported models / alternatives (as in Frappe form).

### Recommended Order

1. Fix `template_version_at_attach` (quick, unblocks Template mode).
2. Add Prompt Template mode UI.
3. Add Knowledge tab.
4. Add Permissions tab.
5. Add `summary_model` and `agent_color`.
6. Add Metadata display and modality filter fix.

---

## 7. Key Risks

1. **Field name mismatch:** `attached_at_version` vs `template_version_at_attach` causes silent data loss.
2. **Incomplete agent configs:** Missing Knowledge and Permissions means agents created from UI lack RAG and access control.
3. **Hidden dependencies:** `agent_knowledge` drives tool registration and context injection; without it, knowledge features are effectively disabled.
4. **Modality filter:** Frontend may hide valid models if `modalities` is multi-value and frontend uses exact match.

---

## Appendix A: Backend Field Reference

| Field | Type | Default | Options / Depends |
|-------|------|---------|-------------------|
| `agent_name` | Data | — | reqd, unique |
| `provider` | Link | — | AI Provider, reqd |
| `model` | Link | — | AI Model, reqd |
| `temperature` | Float | 1 | non_negative |
| `top_p` | Float | 1 | — |
| `description` | Small Text | — | — |
| `instructions` | Code | — | depends_on: prompt_mode==Local |
| `prompt_mode` | Select | Local | Local, Template |
| `agent_prompt` | Link | — | Agent Prompt, depends_on: Template |
| `prompt_version_locked` | Check | 0 | depends_on: Template |
| `template_version_at_attach` | Int | — | read_only, depends_on: Template |
| `copied_from_prompt` | Link | — | Agent Prompt, hidden, read_only |
| `agent_tool` | Table | — | Agent Tool |
| `agent_mcp_server` | Table | — | Agent MCP Server |
| `agent_knowledge` | Table | — | Agent Knowledge |
| `disabled` | Check | 0 | — |
| `allow_chat` | Check | 0 | — |
| `persist_conversation` | Check | 1 | — |
| `persist_user_history` | Check | 1 | — |
| `enable_multi_run` | Check | 0 | — |
| `default_plan` | Table | — | Agent Orchestration Plan, depends_on: enable_multi_run |
| `enable_prompt_caching` | Check | 0 | — |
| `cache_control_type` | Select | ephemeral | ephemeral, auto, depends_on: enable_prompt_caching |
| `cache_system_message` | Check | 1 | depends_on: enable_prompt_caching |
| `cache_conversation_history` | Check | 0 | depends_on: enable_prompt_caching |
| `context_strategy` | Select | Summarize | Summarize, FIFO, None |
| `history_limit` | Int | 20 | non_negative |
| `summary_ratio` | Float | 0.7 | non_negative |
| `summary_model` | Link | — | AI Model |
| `max_knowledge_tokens` | Int | 4000 | non_negative |
| `max_turns` | Int | 20 | non_negative |
| `enable_conversation_data` | Check | 0 | — |
| `autonaming_of_conversation_title` | Check | 1 | — |
| `image_generation_model` | Link | — | AI Model |
| `tts_model` | Link | — | AI Model |
| `tts_voice` | Data | — | — |
| `stt_model` | Link | — | AI Model |
| `agent_color` | Data | — | — |
| `allow_guest` | Check | 0 | — |
| `allowed_users` | Table MultiSelect | — | Agent User |
| `allowed_roles` | Table MultiSelect | — | Agent Role |
| `last_run` | Datetime | — | read_only |
| `total_run` | Int | — | read_only |
| `chef` | Data | — | fetch_from: provider.chef, hidden |
| `slug` | Data | — | fetch_from: provider.slug, hidden |
| `async` | Check | 0 | hidden |

---

## Appendix B: Agent Knowledge Child Table Schema

| Field | Type | Default | Options |
|-------|------|---------|---------|
| `knowledge_source` | Link | — | Knowledge Source, reqd |
| `mode` | Select | Optional | Mandatory, Optional |
| `priority` | Int | 0 | non_negative |
| `max_chunks` | Int | 5 | non_negative |
| `token_budget` | Int | 2000 | non_negative |
| `description` | Small Text | — | — |
