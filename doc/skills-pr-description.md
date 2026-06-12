# Draft PR: Add Skills system for reusable agent capability bundles

**Title:** `draft: feat(skills): add reusable Skills system for agents`

**Branch:** `feature/skills-system`
**Base:** `develop`
**Create URL:** https://github.com/tridz-dev/huf/pull/new/feature/skills-system

---

## Summary

This PR introduces a **Skill** capability layer to Huf. A Skill is a reusable bundle of tools, knowledge sources, prompt templates, MCP servers, and system instructions that can be attached to Agents. Skills can be created manually, imported from Git or a common destination, or provided by installed Frappe apps via a new `huf_skills` hook.

## What changed

### Backend
- **8 new DocTypes:** `Skill`, `Agent Skill`, `Skill Tool`, `Skill Knowledge`, `Skill Prompt`, `Skill MCP Server`, `Skill Category`, `Skill Import Log`.
- Added `agent_skill` child table to the `Agent` DocType.
- New runtime loader at `huf/ai/skills/loader.py` that attaches skill tools, knowledge, MCP servers, and instructions to agents.
- Optional skills are pre-loaded and gated by a system prompt preamble + a runtime `list_skills` tool. Dynamic `load_skill` was intentionally descoped for v1 because the OpenAI Agents SDK fixes the tool list at `Agent` construction.
- Widened `knowledge_search` to include knowledge sources from skills and to search across multiple sources.
- Refactored `create_mcp_tools` to accept an explicit MCP server list so skill MCP servers can be merged in.
- Git/common-destination importer at `huf/ai/skills/importer.py` with manifest validation and broken-link skipping.
- App hook sync at `huf/ai/skills/hooks.py` mirroring the existing `huf_tools` discovery pattern.
- Whitelisted API methods at `huf/ai/skills/api.py`.
- Updated `huf/hooks.py` (`after_migrate`, `after_app_install`, `after_uninstall`) and `huf/install.py` to seed default categories.

### Frontend
- New pages: `SkillsPage`, `SkillFormPage`, `SkillFormPageWrapper`.
- New components: `SkillsTab` (agent form), `SkillImportModal`, `SkillsHeaderActions`.
- New service `skillApi.ts` and types `skill.types.ts`.
- Added `/skills` and `/skills/:id` routes and a sidebar navigation item.
- Extended the Agent form to manage `agent_skill` child rows.

## Key design decisions
- **Optional skill loading:** descoped dynamic `load_skill` for v1. Optional skills are pre-loaded; the agent is instructed to use them only when relevant.
- **Manifest references:** tool/knowledge/prompt/MCP references in imported manifests are validated; missing targets are skipped with warnings.
- **Scope:** site-level for v1; workspace scoping is a follow-up.
- **Versioning:** skills are live-linked for v1; version-locking on agents is a follow-up.

## Follow-up work
- Persist optional skill state across conversation turns.
- Version-lock skills on agents (like prompt templates).
- Workspace-scoped skills.
- Curated marketplace/common destination UI.
- Embedding-based skill auto-pick.

## How to test

See `doc/skills-testing-guide.md` in this branch for step-by-step testing instructions.
