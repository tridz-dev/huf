# Huf Skills System — Phase 1 Gap Analysis

> Branch reviewed: `feature/skills-system`  
> Reference plan: `SKILLS_FUTURE.md` (root) — Phase 1: Packaging & distribution  
> Date: 2026-06-13

---

## 1. What Phase 1 requires

From `SKILLS_FUTURE.md`:

> **Phase 1 — Packaging & distribution.** Skills bundle existing tools/knowledge/prompts, export/import as `.huf`, install from GitHub. No code execution. Establishes the format, UX, and the `huf-skills` repo with 3–5 pre-built skills using existing Huf tools.

Key deliverables from the plan:

| Area | Required |
|------|----------|
| **Backend** | `huf/ai/skills/` package (`loader`, `importer`, `github`, `exporter`, `api`); DocTypes `Skill`, `Agent Skill`, `Skill Category`; merge skill tools/knowledge/instructions at agent construction; `huf/hooks.py` skill sync. |
| **Frontend** | Skills marketplace page; Skill form page; Skills tab on Agent form; Import modal (GitHub / `.huf` upload + dependency warnings); sidebar/routes. |
| **Package format** | `manifest.json` schema; `_index.json` registry schema; `tridz-dev/huf-skills` starter repo with 3–5 skills. |

---

## 2. Executive summary

The `feature/skills-system` branch delivers **most of the DocType, runtime-merge, and UI scaffolding** for Phase 1, but it is **not yet a complete Phase 1 implementation**. The biggest gaps are:

1. **No `.huf` packaging or export.** Phase 1 is defined around a portable `.huf` zip format; the current implementation only imports/exports skill *manifests* (JSON/YAML frontmatter) into Frappe DocTypes.
2. **No `.huf` file upload import.** The import UI only supports Git URLs and typed-in common-destination names, not direct file upload.
3. **No Agent Settings fields for skill destinations / scan cache.** The backend code references `Agent Settings.skill_destinations` and `last_skill_scans`, but those fields do not exist on the DocType, so common-destination configuration has no UI/persistence.
4. **Skill prompts are stored but not loaded at runtime.** The `Skill Prompt` child table exists and is imported, but nothing injects those prompts into the agent system or user messages yet.
5. **No formal package/registry schemas or published `huf-skills` repo.** `_index.json` is not implemented, and there is no sample skill repo bundled or referenced in code.

The runtime behavior for mandatory/optional skills, knowledge widening, MCP merging, and the `list_skills` tool is largely complete.

---

## 3. Detailed gap matrix

### 3.1 Backend

| Item | Status | Notes / Evidence |
|------|--------|------------------|
| DocTypes: `Skill`, `Agent Skill`, `Skill Category` | ✅ Implemented | `huf/huf/doctype/skill/`, `agent_skill/`, `skill_category/`. |
| Child tables: `Skill Tool`, `Skill Knowledge`, `Skill Prompt`, `Skill MCP Server`, `Skill Import Log` | ✅ Implemented | All created; `Skill Import Log` is extra but useful. |
| `agent_skill` child table on `Agent` | ✅ Implemented | `huf/huf/doctype/agent/agent.json` adds a `Skills` tab and `agent_skill` table; controller validates duplicates (`agent.py:_validate_skills`). |
| `huf/ai/skills/loader.py` | ✅ Implemented | Loads all skill tools (`load_all_skill_tools`), mandatory knowledge (`get_mandatory_skill_knowledge`), instructions, optional preamble, MCP servers, and creates the `list_skills` runtime tool. |
| Merge skill tools into `create_agent_tools` | ✅ Implemented | `huf/ai/sdk_tools.py` calls `load_all_skill_tools` after native tools. |
| Merge skill MCP servers | ✅ Implemented | `huf/ai/agent_integration.py:_setup_tools` merges agent + skill MCP server lists; `huf/ai/mcp_client.py:create_mcp_tools` accepts an explicit `mcp_server_names` list. |
| Inject skill instructions / optional preamble | ✅ Implemented | `huf/ai/agent_integration.py:create_agent` appends `get_skill_instructions` and `get_optional_skills_preamble`. |
| Merge mandatory skill knowledge into context | ✅ Implemented | `huf/ai/knowledge/context_builder.py` adds `get_mandatory_skill_knowledge`. |
| Widen `knowledge_search` to skill sources | ✅ Implemented | `huf/ai/knowledge/tool.py:_get_allowed_knowledge_sources` includes skill-attached sources and searches across all allowed sources. |
| `huf/ai/skills/importer.py` | ⚠️ Partial | Git + common-destination + local path import works; `skill.json` and `SKILL.md` frontmatter parsing works; link validation works. **No `.huf` zip import.** |
| `huf/ai/skills/hooks.py` | ✅ Implemented | App-provided skill sync mirrors `huf_tools` pattern; cleanup of orphaned app skills included. |
| `huf/ai/skills/api.py` | ✅ Implemented | Whitelisted wrappers for import, sync, and options. |
| `huf/hooks.py` skill sync | ✅ Implemented | `after_migrate`, `after_app_install`, `after_uninstall` call `huf.ai.skills.hooks.sync_app_skills`. |
| `huf/install.py` default categories | ✅ Implemented | `seed_skill_categories()` creates `General`, `CRM`, `Support`. |
| `github.py` helper module | ❌ Missing | Git logic lives directly in `importer.py`. Not a functional gap for v1. |
| `exporter.py` / `.huf` packaging | ❌ Missing | No backend code creates `.huf` zip files or writes `manifest.json`. |
| `deps.py` / dependency warnings | ❌ Missing | Planned for Phase 2; acceptable for Phase 1. |
| Extend `Agent Tool Function` with `Script`/`Node` source types | ❌ Missing | Listed in the future plan but tied to Phase 2 execution; no impact on Phase 1 packaging. |
| Runtime use of `Skill Prompt` | ❌ Missing | Prompts are imported and stored, but `loader.py` / `agent_integration.py` do not inject them. |

### 3.2 Frontend

| Item | Status | Notes / Evidence |
|------|--------|------------------|
| Skills list page (`SkillsPage`) | ✅ Implemented | `frontend/src/pages/SkillsPage.tsx` with search, status/source filters, grid. |
| Skill form page (`SkillFormPage`) | ✅ Implemented | `frontend/src/pages/SkillFormPage.tsx` supports general fields + tools/knowledge/prompts/MCP tabs. |
| Skills tab on Agent form (`SkillsTab`) | ✅ Implemented | `frontend/src/components/agent/SkillsTab.tsx`; attached to `AgentFormPage` with save/load. |
| Import modal (`SkillImportModal`) | ⚠️ Partial | Supports Git URL and typed common-destination name. **No `.huf` file upload.** Dependency warnings not shown. |
| Export / download button | ❌ Missing | `SkillFormPage` has no export/download action; no `.huf` generation. |
| Skills marketplace page | ❌ Missing | The list page is local-only; there is no browse/search/install UI for a remote registry. |
| Sidebar entry + routes | ✅ Implemented | `frontend/src/components/app-sidebar.tsx` adds "Skills"; `App.tsx` registers `/skills` and `/skills/:id`. |
| Agent Settings skill UI | ❌ Missing | No UI to manage `skill_destinations`, install profiles, or execution gating. |

### 3.3 Package format & distribution

| Item | Status | Notes / Evidence |
|------|--------|------------------|
| `.huf` zip format | ❌ Missing | No zip creation/extraction code. The "package" is currently just a Frappe DocType with linked child rows. |
| `SKILL.md`-primary format | ❌ Not yet adopted | **Decision made (2026-06-13):** `SKILL.md` with standard Anthropic/Claude frontmatter + a `huf:` extension block is the canonical format. No `manifest.json`. The importer already parses `SKILL.md` frontmatter but must be updated to treat the `huf:` block as the authoritative wiring source and stop expecting/generating `manifest.json`. The exporter must write only `SKILL.md`. |
| `_index.json` registry schema | ❌ Missing | Common destinations are hard-coded (`DEFAULT_DESTINATIONS` in `importer.py`) or read from a free-form JSON field that does not exist on the DocType. |
| `tridz-dev/huf-skills` starter repo | ❌ Missing | Default destination points to it, but no repo exists in the codebase and no starter skills ship with Huf. |
| Signed packages / trust model | N/A | Listed as a future decision; current implementation uses domain allowlist (GitHub/GitLab/Bitbucket). |

### 3.4 Runtime / agent behavior

| Item | Status | Notes |
|------|--------|-------|
| Mandatory skills loaded at agent construction | ✅ Implemented | All skill tools are loaded via `load_all_skill_tools`; knowledge injected via `build_knowledge_context`. |
| Optional skills pre-loaded + prompt gating | ✅ Implemented | Optional tools are loaded; preamble instructs the agent to use them only when relevant. Matches the v1 decision. |
| `list_skills` runtime tool | ✅ Implemented | Added in `AgentManager._setup_tools` when skills are attached. |
| Dynamic `load_skill` mid-conversation | ❌ Not planned | Correctly descoped for v1 (documented in plan and testing guide). |
| Skill version-locking on agents | ❌ Not planned | v1 uses live Skill docs; acknowledged in open decisions. |
| Workspace-scoped skills | ❌ Not planned | v1 is site-level. |

---

## 4. Specific code findings

### 4.1 Agent Settings fields are referenced but not defined

`huf/ai/skills/importer.py` (`_get_common_destinations`) and `huf/ai/skills/hooks.py` (`_get_cached_scans` / `_update_cached_scans`) expect fields on `Agent Settings`:

- `skill_destinations` — JSON field for user-configured common destinations.
- `last_skill_scans` — JSON field caching last app hook scan timestamps.

The `Agent Settings` DocType (`huf/huf/doctype/agent_settings/agent_settings.json`) only contains `default_provider` and `default_model`. Because the code uses `hasattr`, it fails gracefully, but:

- Users cannot configure custom common destinations via the UI.
- The default `tridz-dev/huf-skills` destination still works because of the hard-coded `DEFAULT_DESTINATIONS` fallback.
- App-skill scan caching does not persist, so every `after_migrate` does a full re-scan.

### 4.2 Skill prompts are not used at runtime

`Skill Prompt` is a child table and is imported from manifests, but there is no loader function (e.g., `get_skill_prompts`) called from `AgentManager.create_agent` or `resolve_prompt`. For Phase 1 to truly bundle "tools + knowledge + prompts", prompt injection needs to be wired.

### 4.3 Optional skill `auto_load` is hidden from the agent form

The `Agent Skill` child table has an `auto_load` check, but `SkillsTab.tsx` always sets it to `true` and does not expose it. This matches the default behavior but removes the ability to attach a skill without auto-loading its tools.

### 4.4 No sample app-provided skill manifest

The implementation plan mentions an optional `huf/ai/skills/_registry.py` sample; it is not present. This is low-priority but would help validate the `huf_skills` hook path during QA.

---

## 5. What is NOT a Phase 1 gap

These items belong to Phase 2/3 and are correctly absent:

- `run_python` / `run_node` tools.
- RestrictedPython / container execution backends.
- Install profiles (`basic` / `standard` / `full`) and runtime package management.
- `node_executor.py`, `deps.py`.
- Dynamic `load_skill` mid-turn.
- Code signing.

---

## 6. Recommendations to close Phase 1

1. **Add `.huf` export/import.**
   - Backend: create `huf/ai/skills/exporter.py` to zip a Skill doc + linked resources into a `.huf` archive. The archive contains only `SKILL.md` (standard frontmatter + `huf:` block) — no `manifest.json`.
   - Backend: extend `importer.py` to (a) extract `.huf` zip uploads, (b) parse `SKILL.md` frontmatter as the authoritative source (standard fields + `huf:` block), and (c) stop treating `skill.json`/`manifest.json` as primary — those are legacy fallbacks only.
   - Frontend: add a "Download `.huf`" button on `SkillFormPage` and a file-upload tab in `SkillImportModal`.

2. **Formalize the package/registry schemas.**
   - Document `SKILL.md` frontmatter schema (standard fields + `huf:` block fields) and add lightweight YAML validation in the importer.
   - Implement `_index.json` parsing so a repo can declare multiple skills and the UI can render a marketplace.

3. **Add missing `Agent Settings` fields.**
   - Add `skill_destinations` (JSON) and `last_skill_scans` (JSON) to `Agent Settings`.
   - Optionally add a UI section to manage destinations and trigger sync.

4. **Wire `Skill Prompt` at runtime.**
   - Add `get_skill_prompts(agent_name)` to `loader.py` and inject system/user prompts in `AgentManager.create_agent` / `resolve_prompt`.

5. **Ship starter skills.**
   - Create the `tridz-dev/huf-skills` repo with 3–5 Phase-1-compatible skills (e.g., PDF helper using existing tools, HTTP helper, Data helper) so the default common destination is immediately usable.

6. **Add minimal tests.**
   - Unit tests for manifest parsing (`_parse_skill_manifest`), link resolution (`_resolve_link`), and loader filtering would de-risk the branch before merging.

---

## 7. Verdict

**Phase 1 is ~60–70% complete.** The core runtime-merge plumbing and UI scaffolding are in place and functional. The remaining work is mostly the `.huf` packaging layer, registry/discovery polish, Agent Settings persistence, and prompt wiring — all of which are central to the stated Phase 1 goal of "packaging & distribution."
