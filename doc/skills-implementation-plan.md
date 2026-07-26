# Huf Skills System — Vetted Implementation Plan

> Draft PR branch: `feature/skills-system`  
> Goal: add a reusable Skill capability layer to Huf with UI, Git import, common-destination import, app hooks, and agent awareness.

---

## 1. What a Skill Is

A **Skill** is a reusable bundle of agent capabilities:

- **Tools** – references to `Agent Tool Function` docs
- **Knowledge** – references to `Knowledge Source` docs (Mandatory or Optional)
- **Prompts** – references to `Agent Prompt` templates
- **MCP servers** – references to `MCP Server` docs
- **Instructions** – plain text guidelines injected into the agent system prompt

Skills can be:

1. Created manually in the UI.
2. Imported from a Git repo (`https://github.com/org/repo`, sub-path `skills/`).
3. Imported from a configurable **common skill destination** (curated GitHub repo list, default: `tridz-dev/huf-skills`).
4. Provided by installed Frappe apps via a `huf_skills` hook.

Agents attach skills through a child table `Agent Skill` with mode **Mandatory** (always loaded) or **Optional** (pre-loaded but gated by a system prompt preamble). Agents are made aware of optional skills via that preamble and a `list_skills` runtime tool.

---

## 2. Decisions (Open Questions Resolved)

| Question | Decision for draft PR |
|----------|------------------------|
| Optional skill persistence | Optional skills are pre-loaded at agent construction (tools/knowledge/MCP are available), but the agent is instructed via a system prompt preamble to *use* an optional skill only when relevant. Persistent per-conversation skill state is a follow-up. |
| Skill versioning on agents | v1 uses the live Skill doc. Version-locking (`skill_version_at_attach`) is a follow-up. |
| Scope | Site-level for v1, matching current `Knowledge Source` default scope. Workspace scoping is a follow-up. |
| Common skill destination | A JSON list in `Agent Settings` (`skill_destinations`). Default entry points to `https://github.com/tridz-dev/huf-skills`. |
| Skill manifest format | **`SKILL.md`-primary.** `SKILL.md` with standard Anthropic/Claude frontmatter (`name`, `description`, `allowed-tools`, `compatibility`) plus a `huf:` extension block for Huf-specific wiring (tools, knowledge, prompts, mcp_servers, version, author, category). No separate `manifest.json`. Claude/Kimi ignore the `huf:` block; Huf reads everything. Skills from skills.sh with no `huf:` block import as instructions-only and tools are wired manually. |
| Permissions | Standard Frappe DocType permissions for v1. No custom skill permission hooks yet. |
| Auto-pick mechanism | System prompt preamble lists optional skills with descriptions. A `list_skills` runtime tool returns the same list. No embedding-based retrieval in v1. Dynamic `load_skill` tool is descoped for v1 because tools cannot be added to a running `Agent` instance mid-turn. |
| MCP in skills | v1 includes a child table linking `MCP Server` docs. The loader merges skill MCP servers into the effective server list before calling the existing MCP client. |

---

## 3. New DocTypes

### 3.1 `Skill`

| Field | Type | Notes |
|-------|------|-------|
| `skill_name` | Data, unique, required | machine id, snake_case |
| `title` | Data, required | human label |
| `description` | Small Text | shown in UI and to agents |
| `skill_category` | Link → Skill Category | grouping |
| `version` | Data | free text, e.g. `1.0.0` |
| `author` | Data | author or org |
| `source_type` | Select: Local / Git / Common Destination / App Provided | required |
| `source_url` | Data | Git URL or destination URL |
| `source_path` | Data | sub-path inside repo |
| `source_ref` | Data | branch/tag/commit |
| `provider_app` | Data | app name if from `huf_skills` hook |
| `status` | Select: Draft / Active / Error / Disabled | default Active |
| `skill_icon` | Data | icon identifier |
| `instructions` | Long Text | system prompt text injected when skill is loaded |
| `auto_load` | Check | default 1 for Mandatory skills |

Child tables: `skill_tools`, `skill_knowledge`, `skill_prompts`, `skill_mcp_servers`.

### 3.2 `Skill Tool` (child table)

| Field | Type |
|-------|------|
| `tool` | Link → Agent Tool Function, required |
| `description` | Small Text (override) |
| `required` | Check |

### 3.3 `Skill Knowledge` (child table)

| Field | Type |
|-------|------|
| `knowledge_source` | Link → Knowledge Source, required |
| `mode` | Select: Mandatory / Optional, default Mandatory |
| `max_chunks` | Int, default 5 |
| `token_budget` | Int, default 2000 |

### 3.4 `Skill Prompt` (child table)

| Field | Type |
|-------|------|
| `prompt` | Link → Agent Prompt, required |
| `usage` | Select: System / User, default System |

### 3.5 `Skill MCP Server` (child table)

| Field | Type |
|-------|------|
| `mcp_server` | Link → MCP Server, required |
| `enabled` | Check, default 1 |

### 3.6 `Agent Skill` (child table in `Agent`)

| Field | Type |
|-------|------|
| `skill` | Link → Skill, required |
| `mode` | Select: Mandatory / Optional, default Mandatory |
| `auto_load` | Check, default 1 |
| `priority` | Int, default 0 |
| `description` | Small Text (override) |

### 3.7 `Skill Category`

Same pattern as `Agent Prompt Category`.

### 3.8 `Skill Import Log` (optional, for audit)

| Field | Type |
|-------|------|
| `skill` | Link → Skill |
| `source_url` | Data |
| `source_ref` | Data |
| `status` | Select: Success / Error |
| `error_message` | Small Text |

---

## 4. Backend Modules

### 4.1 `huf/ai/skills/loader.py`

Core responsibility: turn a Skill definition into concrete runtime capabilities.

```python
def get_agent_skills(agent_name: str, mode: str = None) -> list[SkillDoc]:
    """Return Skill docs attached to an agent, optionally filtered by mode."""

def get_agent_skill_mcp_servers(agent_name: str) -> list[str]:
    """Return enabled MCP server names from all attached skills."""

def load_mandatory_skill_tools(agent_doc, user: str) -> list[FunctionTool]:
    """Return FunctionTool instances from all Mandatory skill tools."""

def get_mandatory_skill_knowledge(agent_name: str) -> list[dict]:
    """Return mandatory knowledge source configs from skills."""

def get_skill_instructions(agent_name: str) -> str:
    """Concatenate instructions from all mandatory and optional skills."""

def get_optional_skills_preamble(agent_name: str) -> str:
    """Return a system prompt section listing optional skills."""

def create_list_skills_tool(agent_name: str):
    """Build a runtime list_skills tool."""
```

### 4.2 `huf/ai/skills/importer.py`

```python
@frappe.whitelist()
def import_skill_from_git(repo_url: str, path: str = "skills", ref: str = "main") -> dict:
    """Clone a repo to a temp dir, parse manifests, create/update Skill docs."""

@frappe.whitelist()
def import_skill_from_common_destination(destination_name: str) -> dict:
    """Import from a configured common destination."""

def import_skill_from_path(path: str, source_type="Local", source_url=None, source_ref=None) -> "Skill":
    """Parse a single skill directory or SKILL.md file."""
```

Skill manifest (`SKILL.md` — canonical format):

```markdown
---
name: huf-sales
description: Sales CRM operations. Use when user asks about leads, orders, or customers.
compatibility:
  requires: []          # Phase 2+: list pip packages here

huf:
  version: "1.0.0"
  author: "Tridz"
  category: "CRM"
  tools:
    - get_sales_orders
    - create_lead
  knowledge:
    - source: "Sales Playbook"
      mode: Mandatory
      max_chunks: 5
  prompts:
    - prompt: "Sales Response Template"
      usage: System
  mcp_servers:
    - frappe-crm-mcp
---

# Huf Sales Skill

When the user asks about sales pipelines, leads, or orders...
```

> The `huf:` block is ignored by Claude/Kimi. Standard fields (`name`, `description`) are compatible with skills.sh. A skill from skills.sh with no `huf:` block imports as instructions-only; tools are wired manually afterward.

**Manifest link resolution strategy**: when a manifest references a tool, knowledge source, prompt, or MCP server by name, the importer must verify the target DocType record exists. If it does not exist, log a warning and skip that item (do not create broken Link fields). In a later iteration we can add a "create stubs" option.

### 4.3 `huf/ai/skills/hooks.py`

Mirror the `huf_tools` sync pattern.

```python
def sync_app_skills(apps_to_scan=None, use_cache=True) -> dict:
    """Scan installed apps for huf_skills hooks and sync Skill docs."""
```

Hook format in an app's `hooks.py`:

```python
huf_skills = [
    {
        "skill_name": "my_app_skill",
        "title": "My App Skill",
        "description": "...",
        "function_path": "my_app.skills.manifest.get_skill_definition",
    }
]
```

The referenced function returns the skill manifest dict.

### 4.4 `huf/ai/skills/api.py`

Whitelisted methods used by the UI:

```python
@frappe.whitelist()
def import_skill_from_git(repo_url, path="skills", ref="main")

@frappe.whitelist()
def import_skill_from_common_destination(destination_name)

@frappe.whitelist()
def sync_app_skills()

@frappe.whitelist()
def get_skill_options()
```

---

## 5. Integration Points

### 5.1 `huf/ai/sdk_tools.py` — `create_agent_tools`

After native tools are loaded, append tools from mandatory skills:

```python
from huf.ai.skills.loader import load_mandatory_skill_tools
skill_tools = load_mandatory_skill_tools(agent, frappe.session.user)
if skill_tools:
    tools.extend(skill_tools)
```

### 5.2 `huf/ai/agent_integration.py` — `AgentManager._setup_tools` and `create_agent`

All skill tools (mandatory and optional) are added in `_setup_tools()` so they are included in the tool-description block built by `create_agent()`:

1. In `_setup_tools()`, after native tools and knowledge tools, add skill tools from all attached skills (`load_all_skill_tools`).
2. In `_setup_tools()`, also merge skill MCP servers into the effective MCP server list before calling `create_mcp_tools`.
3. In `create_agent()`, after `resolve_prompt`:
   - Append mandatory skill instructions.
   - Append optional skill preamble.

```text
Optional skills available. Only use an optional skill when the user's request clearly matches its description:
- huf-sales: Sales CRM operations
- huf-marketing: Campaign helpers
```

### 5.3 `huf/ai/knowledge/context_builder.py` — `build_knowledge_context`

Merge mandatory knowledge from skills with agent-level mandatory knowledge:

```python
mandatory_sources = get_mandatory_knowledge(agent_name)
mandatory_sources += get_mandatory_skill_knowledge(agent_name)
```

### 5.4 `huf/ai/knowledge/tool.py` — `knowledge_search` scope

Two related changes:

1. **Include skill-attached sources** in the list of sources an agent is allowed to search.
2. **Search across multiple sources** instead of collapsing to the highest-priority single source. The retriever already supports a list; plumb it through.

Update `handle_knowledge_search()` and `handle_get_knowledge_sources()` so that when `knowledge_source` is omitted they build `allowed_sources = agent_knowledge_sources + skill_knowledge_sources` and pass that list to the retriever. This makes skill knowledge usable via the runtime `knowledge_search` tool.

### 5.5 `huf/ai/mcp_client.py` — skill MCP servers

Refactor `create_mcp_tools(agent)` to accept an optional `mcp_server_names` list. `loader.py` will compute the merged list from `agent.agent_mcp_server` plus skill MCP servers, then call `create_mcp_tools(agent, mcp_server_names=merged)`.

### 5.6 `huf/hooks.py`

Change `after_migrate` to a list and append skill sync:

```python
after_migrate = [
    "huf.install.after_migrate",
    "huf.ai.skills.hooks.sync_app_skills",
]
```

Also add skill sync to `after_app_install` if not already covered.

Add skill cleanup on uninstall:

```python
after_uninstall = [
    "huf.ai.tool_registry.sync_app_tools",
    "huf.ai.skills.hooks.sync_app_skills",
]
```

### 5.7 `huf/install.py`

After install/migrate, ensure default `Skill Category` records exist (e.g. `General`, `CRM`, `Support`).

---

## 6. Frontend

### 6.1 New pages

- `frontend/src/pages/SkillsPage.tsx` — list skills with search/filter.
- `frontend/src/pages/SkillFormPage.tsx` — create/edit skill and assign tools/knowledge/prompts/MCP.
- `frontend/src/components/skills/SkillImportModal.tsx` — import from Git / common destination.

### 6.2 New service & types

- `frontend/src/services/skillApi.ts`
- `frontend/src/types/skill.types.ts`

### 6.3 Agent form updates

- Add a `skills` tab in `AgentFormPage.tsx`.
- Create `frontend/src/components/agent/SkillsTab.tsx`.
- Extend `AgentFormValues` / `agentFormSchema` and `mapAgentDocToFormValues` for `agent_skill`.
- Include `agent_skill` in the save payload.

### 6.4 Routing & navigation

- Add `/skills` and `/skills/:id` in `App.tsx`.
- Add `SkillsHeaderActions`.
- Add a sidebar entry in `components/app-sidebar.tsx`.

---

## 7. Agent Awareness & Auto-Pick

Two mechanisms for v1:

1. **System prompt preamble** lists optional skills with descriptions and tells the agent to use them only when relevant.
2. **`list_skills` runtime tool** returns the same list.

Dynamic `load_skill` is **descoped for v1** because the OpenAI Agents SDK fixes the tool list at `Agent` construction; mutating `agent.tools` mid-run does not expose new callable tools to the model for that turn. Instead, optional skill tools/knowledge/MCP are **pre-loaded** at agent construction, and the agent is instructed to invoke them only when the request matches the skill description. This is simpler and actually works.

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Circular import between `sdk_tools` and `skills.loader` | Keep `loader.py` imports lazy; import inside functions. Do not import `sdk_tools` from `loader.py` at module level. |
| DocType naming collisions | Use `Skill` prefix; child tables named `Skill Xxx`. |
| Breaking existing agent runs | Only append skill content; do not replace existing tool/knowledge logic. Feature-gate via new DocTypes. |
| Git import fails / SSRF | Use `tempfile`, validate URL scheme (`https`), enforce domain allowlist for common destinations, set subprocess timeout and shallow clone, wrap in try/except. |
| Frontend child-table save mapping | Mirror existing `agent_tool`/`agent_knowledge` patterns exactly. |
| MCP server not linked at runtime | Refactor `create_mcp_tools(agent, mcp_server_names=None)`; loader passes the merged list from agent + skills. |
| Skill knowledge not searchable | Widen `knowledge_search` scope to include knowledge sources from all attached skills. |
| `SKILL.md` imports create broken links | Importer validates referenced tools/knowledge/prompts/MCP exist in the `huf:` block; skips missing items and logs warnings. Skills from skills.sh with no `huf:` block never have broken links — they are instructions-only. |
| Dynamic `load_skill` infeasible | Descoped for v1; optional skills are pre-loaded and gated by the system prompt preamble. |

---

## 9. Phase 1 Minimal Checklist (Draft PR)

### Backend
1. Create DocTypes: `Skill`, `Agent Skill`, `Skill Tool`, `Skill Knowledge`, `Skill Prompt`, `Skill MCP Server`, `Skill Category`, `Skill Import Log`.
2. Add `agent_skill` child table to `Agent` DocType JSON and controller validation.
3. Implement `huf/ai/skills/loader.py` with mandatory skill tool/knowledge/instruction loading, optional skill preamble, MCP server merging, and `list_skills` runtime tool.
4. Wire `create_agent_tools` to include all attached skill tools (mandatory + optional).
5. Refactor `create_mcp_tools(agent, mcp_server_names=None)` and wire loader to pass merged agent + skill MCP servers.
6. Wire `AgentManager.create_agent` to inject skill instructions and optional skill preamble.
7. Wire `build_knowledge_context` to include mandatory skill knowledge.
8. Update `huf/ai/knowledge/tool.py` so `knowledge_search` covers skill-attached knowledge sources:
   - 8a. Include skill-attached sources in the agent's allowed source list.
   - 8b. Search across multiple sources (use the retriever's list support) instead of collapsing to the highest-priority single source.
9. Implement `huf/ai/skills/importer.py` for Git + local path + `.huf` zip + `SKILL.md`-primary parsing (read `name`/`description` from standard frontmatter, read `huf:` block for wiring), with link validation. `manifest.json` is not generated or consumed — `SKILL.md` is the only file format.
10. Implement `huf/ai/skills/hooks.py` for `huf_skills` app hook sync.
11. Implement `huf/ai/skills/api.py` whitelisted methods.
12. Update `huf/hooks.py` (`after_migrate`, `after_app_install`, `after_uninstall`) and `huf/install.py` (default categories).

### Frontend
13. Create `frontend/src/types/skill.types.ts`.
14. Create `frontend/src/services/skillApi.ts`.
15. Create `SkillsPage`, `SkillFormPage`, `SkillImportModal`.
16. Create `SkillsTab` for the agent form.
17. Update `AgentFormPage` tab config, save payload, and `mapAgentDocToFormValues`.
18. Update `App.tsx` routes, header actions, and sidebar.

### Polish
19. Add a sample app-provided skill with a `SKILL.md` in `huf/ai/skills/_registry.py` (optional).
20. Run `pre-commit` / lint on new frontend files.
21. Commit and push `feature/skills-system`.

---

## 10. Key Files

### Create
- `huf/huf/doctype/skill/`
- `huf/huf/doctype/agent_skill/`
- `huf/huf/doctype/skill_tool/`
- `huf/huf/doctype/skill_knowledge/`
- `huf/huf/doctype/skill_prompt/`
- `huf/huf/doctype/skill_mcp_server/`
- `huf/huf/doctype/skill_category/`
- `huf/huf/doctype/skill_import_log/`
- `huf/ai/skills/loader.py`
- `huf/ai/skills/importer.py`
- `huf/ai/skills/hooks.py`
- `huf/ai/skills/api.py`
- `huf/ai/skills/__init__.py`
- `frontend/src/pages/SkillsPage.tsx`
- `frontend/src/pages/SkillFormPage.tsx`
- `frontend/src/components/skills/SkillsTab.tsx`
- `frontend/src/components/skills/SkillImportModal.tsx`
- `frontend/src/services/skillApi.ts`
- `frontend/src/types/skill.types.ts`

### Modify
- `huf/huf/doctype/agent/agent.json`
- `huf/huf/doctype/agent/agent.py`
- `huf/ai/sdk_tools.py`
- `huf/ai/agent_integration.py`
- `huf/ai/knowledge/context_builder.py`
- `huf/ai/knowledge/tool.py` (widen search scope)
- `huf/ai/mcp_client.py` (refactor `create_mcp_tools` signature)
- `huf/hooks.py`
- `huf/install.py`
- `frontend/src/App.tsx`
- `frontend/src/pages/AgentFormPage.tsx`
- `frontend/src/components/agent/types.ts`
- `frontend/src/types/agent.types.ts`
- `frontend/src/services/agentApi.ts`
- `frontend/src/components/app-sidebar.tsx`
