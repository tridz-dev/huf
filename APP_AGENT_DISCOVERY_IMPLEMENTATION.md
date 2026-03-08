# HUF App Agent Discovery — Implementation Reference

> Implementation of the specification in `APP_AGENT_DISCOVERY.md`.
> This document describes the code, architecture, APIs, and logic created for testing and future maintenance.

---

## 1. Overview

The App Agent Discovery system allows external Frappe apps to declare AI capabilities (agents, tools, prompts, providers, models, knowledge sources, triggers) via JSON files in a `huf/` folder. HUF discovers, validates, normalises, and syncs these definitions into DocTypes automatically.

---

## 2. Module Structure

```
huf/ai/app_registry/
├── __init__.py          # Public exports
├── discovery.py         # Orchestration, whitelisted APIs
├── loader.py            # File scanning, JSON loading
├── validator.py         # Type-specific validation
├── normaliser.py        # Payload transformation
├── importer.py          # DocType upsert
├── exporter.py          # Export to JSON
└── cache.py             # Cache management
```

---

## 3. Files Created or Modified

### 3.1 New Files

| Path | Purpose |
|------|---------|
| `huf/ai/app_registry/__init__.py` | Module init, exports `discover_app_definitions`, `get_app_discovery_status` |
| `huf/ai/app_registry/loader.py` | `scan_app()`, `load_definition()`, `get_huf_dir_for_app()` |
| `huf/ai/app_registry/cache.py` | `_get_cache()`, `_set_cache()`, `compute_file_hash()`, `should_scan_app()`, `update_scan_cache()`, `clear_scan_cache()` |
| `huf/ai/app_registry/validator.py` | `validate()`, `ValidationResult`, type-specific validators |
| `huf/ai/app_registry/normaliser.py` | `normalise()`, type-specific normalisers |
| `huf/ai/app_registry/importer.py` | `upsert_definition()`, `import_definition()` |
| `huf/ai/app_registry/discovery.py` | `discover_app_definitions()`, `_import_app_definitions()` |
| `huf/ai/app_registry/exporter.py` | `export_definition()`, `export_agent_bundle()` |
| `frontend/src/services/appDiscoveryApi.ts` | `getAppDiscoveryStatus()`, `discoverAppDefinitions()`, `rebuildAppDefinitions()` |
| `frontend/src/pages/AppDefinitionsPage.tsx` | Manual Sync UI page |

### 3.2 Modified Files

| Path | Changes |
|------|---------|
| `huf/install.py` | Call `discover_app_definitions()` in `after_migrate` and `after_install` |
| `huf/huf/doctype/agent/agent.json` | Added `source_app`, `source_file` |
| `huf/huf/doctype/agent_tool_function/agent_tool_function.json` | Added `source_app`, `source_file` |
| `huf/huf/doctype/agent_prompt/agent_prompt.json` | Added `source_app`, `source_file` |
| `huf/huf/doctype/ai_provider/ai_provider.json` | Added `source_app`, `source_file` |
| `huf/huf/doctype/ai_model/ai_model.json` | Added `source_app`, `source_file` |
| `huf/huf/doctype/knowledge_source/knowledge_source.json` | Added `source_app`, `source_file` |
| `huf/huf/doctype/agent_trigger/agent_trigger.json` | Added `source_app`, `source_file` |
| `huf/huf/doctype/agent_settings/agent_settings.json` | Added `last_definition_scans` (JSON cache) |
| `frontend/src/App.tsx` | Route `/app-definitions`, import `AppDefinitionsPage` |
| `frontend/src/components/app-sidebar.tsx` | Nav item "App Definitions" |
| `frontend/src/layouts/UnifiedHeader.tsx` | Page title for `/app-definitions` |

---

## 4. APIs

### 4.1 Backend (Whitelisted)

| Method | Args | Returns |
|--------|------|---------|
| `huf.ai.app_registry.discovery.discover_app_definitions_api` | `app_name?: str`, `use_cache?: bool` | `{ synced_apps, total_definitions, by_type, errors, error_count, warnings, warning_count }` |
| `huf.ai.app_registry.discovery.get_app_discovery_status` | — | `[{ app, has_huf_dir, definition_counts, last_sync, files }]` |
| `huf.ai.app_registry.discovery.rebuild_app_definitions` | — | Same as `discover_app_definitions_api` |
| `huf.ai.app_registry.exporter.export_definition_api` | `doctype: str`, `name: str` | `{ filename, content }` |
| `huf.ai.app_registry.exporter.export_agent_bundle_api` | `agent_name: str` | `{ "path": "json_content", ... }` |

### 4.2 Frontend Service

| Function | Purpose |
|----------|---------|
| `getAppDiscoveryStatus()` | Fetch status for all apps |
| `discoverAppDefinitions(appName?, useCache?)` | Run sync |
| `rebuildAppDefinitions()` | Clear cache and full re-sync |

---

## 5. Logic and Methods

### 5.1 Load Order (Dependency Resolution)

```
Phase 1: providers
Phase 2: models
Phase 3: prompts
Phase 4: tools
Phase 5: knowledge
Phase 6: agents
Phase 7: triggers
```

### 5.2 Key Field Mapping (Upsert)

| Type | DocType | Key Field |
|------|---------|------------|
| provider | AI Provider | provider_name |
| model | AI Model | model_name |
| prompt | Agent Prompt | slug |
| tool | Agent Tool Function | tool_name |
| knowledge | Knowledge Source | source_name |
| agent | Agent | agent_name |
| trigger | Agent Trigger | trigger_name |

### 5.3 Validation Rules

- **Provider**: `provider_name` required
- **Model**: `model_name`, `provider` required
- **Prompt**: `title`, `slug`, `prompt_body` required
- **Tool**: `tool_name`, `description` required; `function_path` required for Custom/App Provided; `function_path` must be importable and callable
- **Knowledge**: `source_name` required
- **Agent**: `agent_name`, `provider`, `model` required; warnings for missing provider/model
- **Trigger**: `trigger_name`, `agent` required; agent must exist; Doc Event requires `reference_doctype`, `doc_event`; Schedule requires `scheduled_interval`

### 5.4 Cache

- Stored in `Agent Settings.last_definition_scans` (JSON)
- Per-app: `{ timestamp, file_hash }`
- File hash: SHA256 of `path:mtime` for all definition files
- `should_scan_app()`: skip if hash unchanged
- `clear_scan_cache()`: used by Rebuild

### 5.5 Provenance

- `source_app`: App that provided the definition
- `source_file`: Relative path (e.g. `crm/huf/tools/create_lead.tool.json`)
- Never overwrite `api_key` on AI Provider when updating from file

---

## 6. Folder Convention

```
<app_name>/<app_name>/huf/
  agents/       *.json → Agent
  tools/        *.json → Agent Tool Function
  prompts/      *.json → Agent Prompt
  providers/    *.json → AI Provider
  models/       *.json → AI Model
  knowledge/    *.json → Knowledge Source
  triggers/     *.json → Agent Trigger
```

---

## 7. Integration Points

| Hook / Event | Action |
|--------------|--------|
| `after_migrate` | `sync_discovered_tools()` then `discover_app_definitions(use_cache=False)` |
| `after_install` | `discover_app_definitions(use_cache=False)` |
| Manual Sync (UI) | `discover_app_definitions_api()` or `rebuild_app_definitions()` |

---

## 8. Coexistence with Tool Registry

- `huf_tools` hook: processed first by `sync_discovered_tools()`
- File-based tools: processed by `discover_app_definitions()` (after migrate)
- File-based definitions take precedence for duplicate `tool_name`

---

## 9. Testing Checklist

1. **Create test app** with `huf/agents/`, `huf/tools/` and sample JSON files
2. **Run `bench migrate`** — definitions should sync
3. **Open App Definitions page** (`/huf/app-definitions`) — verify status
4. **Sync All** — verify no errors
5. **Export** — call `export_definition_api("Agent", "Test Agent")` and `export_agent_bundle_api("Test Agent")`
6. **Provenance** — check `source_app`, `source_file` on synced docs
7. **Provider** — ensure `api_key` is never overwritten from file

---

## 10. Future Extensions

- Orphan detection and cleanup UI
- Export buttons on Agent/Tool/Prompt forms
- `flows/` folder support
- Version migration logic
