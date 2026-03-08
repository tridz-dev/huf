# HUF App Agent Discovery System

> **Status**: Specification &mdash; not yet implemented.
> This document is the authoritative design reference for the file-based agent discovery system.
> Implementation work should follow this specification exactly.

---

## Table of Contents

1. [Objective](#1-objective)
2. [Design Goals](#2-design-goals)
3. [Discovery Mechanism](#3-discovery-mechanism)
4. [Supported Definition Types](#4-supported-definition-types)
5. [JSON Definition Philosophy](#5-json-definition-philosophy)
6. [Agent Definition Schema](#6-agent-definition-schema)
7. [Prompt Definition Schema](#7-prompt-definition-schema)
8. [Tool Definition Schema](#8-tool-definition-schema)
9. [Provider Definition Schema](#9-provider-definition-schema)
10. [Model Definition Schema](#10-model-definition-schema)
11. [Knowledge Definition Schema](#11-knowledge-definition-schema)
12. [Trigger Definition Schema](#12-trigger-definition-schema)
13. [File Naming Convention](#13-file-naming-convention)
14. [Envelope Format](#14-envelope-format)
15. [Discovery Engine](#15-discovery-engine)
16. [Import Pipeline](#16-import-pipeline)
17. [Validation Layer](#17-validation-layer)
18. [Upsert Strategy](#18-upsert-strategy)
19. [Dependency Resolution](#19-dependency-resolution)
20. [App Isolation and Provenance](#20-app-isolation-and-provenance)
21. [Sync Algorithm](#21-sync-algorithm)
22. [UI Export Feature](#22-ui-export-feature)
23. [Versioning Strategy](#23-versioning-strategy)
24. [Failure Handling](#24-failure-handling)
25. [Manual Sync UI](#25-manual-sync-ui)
26. [Caching](#26-caching)
27. [Security](#27-security)
28. [Implementation Modules](#28-implementation-modules)
29. [Relationship to Existing Tool Registry](#29-relationship-to-existing-tool-registry)
30. [Developer Experience](#30-developer-experience)
31. [End-to-End Example](#31-end-to-end-example)
32. [Required App Declaration](#32-required-app-declaration)
33. [Future Extensions](#33-future-extensions)
34. [Glossary](#34-glossary)
35. [Summary](#35-summary)

---

## 1. Objective

Enable **external Frappe apps** (ERPNext, CRM, HRMS, Healthcare, custom apps, etc.) to
**declare AI capabilities** &mdash; agents, tools, prompts, providers, models, knowledge
sources, and triggers &mdash; inside their own repositories using plain JSON files.

**When HUF is installed:**

- HUF automatically **discovers** these definition files at well-known paths.
- Validates and normalises each definition.
- Syncs them into the corresponding **HUF DocTypes**.
- Makes them immediately usable by agents, flows, and the chat UI.

**When HUF is _not_ installed:**

- The external app continues to function normally.
- The `huf/` folder and its JSON files are inert; they carry no runtime cost.

The system behaves analogously to **Frappe DocType discovery**: Frappe finds DocType
JSON files by scanning `<app>/<module>/doctype/<name>/<name>.json`. HUF finds AI
definitions by scanning `<app>/huf/<type>/<file>.json`.

---

## 2. Design Goals

| # | Goal | Rationale |
|---|------|-----------|
| 1 | **Zero configuration for app developers** | Drop JSON files into a folder; no registration code required. |
| 2 | **No `hooks.py` dependency** | Definitions are discovered by filesystem convention, not by hook declarations. Existing `huf_tools` hook remains supported but is not required. |
| 3 | **File-based declarative architecture** | JSON files are version-controlled, diffable, reviewable, and portable. |
| 4 | **Compatible with existing HUF DocTypes** | JSON schemas mirror DocType field structures so import/export requires minimal mapping. |
| 5 | **Exportable from UI** | Any definition created in the HUF UI can be exported back to the JSON file format for inclusion in an app. |
| 6 | **Resilient** | Discovery errors never break `bench migrate` or app installation. Bad files are logged and skipped. |
| 7 | **Future extensible** | New definition types (flows, guardrails, skills) can be added by creating a new subfolder and a loader, with no changes to the core engine. |

---

## 3. Discovery Mechanism

### 3.1 Folder Convention

Any installed Frappe app may include a `huf/` directory inside its Python package root.
Inside `huf/`, subdirectories map one-to-one to definition types:

```
<app_name>/
  <app_name>/
    huf/
      agents/          # Agent definitions
      prompts/         # Prompt template definitions
      tools/           # Tool (Agent Tool Function) definitions
      providers/       # AI Provider definitions
      models/          # AI Model definitions
      knowledge/       # Knowledge Source definitions
      triggers/        # Agent Trigger definitions
```

Concrete example for a CRM app:

```
crm/
  crm/
    huf/
      agents/
        lead_assistant.agent.json
      prompts/
        lead_summary.prompt.json
      tools/
        create_lead.tool.json
        get_recent_leads.tool.json
      knowledge/
        sales_playbook.knowledge.json
```

All subdirectories are optional. An app only needs to include the folders for the
definition types it provides. An empty `huf/` directory is valid and will be scanned
without error.

### 3.2 Discovery Rule

When HUF runs a sync cycle it iterates over every installed app:

```python
import frappe, os

for app in frappe.get_installed_apps():
    app_path = frappe.get_app_path(app)          # e.g. /bench/apps/crm/crm
    huf_dir  = os.path.join(app_path, "huf")
    if os.path.isdir(huf_dir):
        scan_app_definitions(app, huf_dir)
```

Only the **app's own package directory** is scanned (i.e. `crm/crm/huf/`, not
`crm/huf/`). This mirrors how Frappe locates modules inside apps.

### 3.3 Trigger Points

Discovery runs automatically on three occasions:

| Trigger | When | Scope |
|---------|------|-------|
| `after_migrate` | After `bench migrate` completes | Full scan of all installed apps |
| `after_install` | After HUF itself is installed | Full scan of all installed apps |
| Manual button | User clicks **"Sync App Definitions"** in the HUF UI | Full or per-app scan |

Additionally, an incremental scan can be triggered programmatically:

```python
# Sync definitions from a specific app
from huf.ai.app_registry.discovery import sync_app_definitions
sync_app_definitions(app_name="crm")
```

### 3.4 Discovery API

The public, whitelisted entry point:

```python
@frappe.whitelist()
def discover_app_definitions(app_name=None):
    """
    Discover and sync AI definitions from installed apps.

    Args:
        app_name: If provided, only scan this app. Otherwise scan all installed apps.

    Returns:
        dict with keys: synced_apps, total_definitions, errors, error_count
    """
```

---

## 4. Supported Definition Types

| Folder | Definition Type | Target HUF DocType | Purpose |
|--------|----------------|-------------------|---------|
| `agents/` | Agent | **Agent** | Full agent definitions with instructions, model, tools, knowledge |
| `tools/` | Tool | **Agent Tool Function** | Tool definitions (Custom Function, App Provided, CRUD, HTTP) |
| `prompts/` | Prompt | **Agent Prompt** | Reusable prompt templates with versioning |
| `providers/` | Provider | **AI Provider** | AI service provider declarations (credentials added separately) |
| `models/` | Model | **AI Model** | Model declarations linked to providers |
| `knowledge/` | Knowledge | **Knowledge Source** | Knowledge source definitions for RAG |
| `triggers/` | Trigger | **Agent Trigger** | Event-driven, scheduled, or webhook triggers |

Each folder is scanned for `*.json` files only. Non-JSON files are ignored. Nested
subdirectories within a type folder are **not** scanned (flat structure only).

---

## 5. JSON Definition Philosophy

The JSON schema for each definition type **mirrors the corresponding HUF DocType
fields** as closely as possible.

**Why:**

- Minimal mapping logic between file and DocType.
- Export from UI produces a file that can be imported without transformation.
- Developers familiar with HUF DocTypes can author definition files without learning a
  new schema.

**Rules:**

1. Field names in JSON match DocType `fieldname` values (snake_case).
2. Link fields use the **name** (primary key) of the linked document, not internal IDs.
3. Child table fields are represented as arrays of objects.
4. Read-only, auto-calculated, and layout fields are omitted.
5. Every definition file must include a `"type"` field identifying the definition type.

---

## 6. Agent Definition Schema

**Target DocType:** Agent

**File location:** `<app>/huf/agents/<name>.agent.json`

### 6.1 Full Schema

```json
{
  "type": "agent",

  "agent_name": "CRM Lead Assistant",
  "description": "Helps sales reps manage and qualify leads",

  "provider": "openai",
  "model": "gpt-4o-mini",

  "prompt_mode": "Local",
  "instructions": "You are a CRM assistant specialising in lead management...",

  "agent_prompt": null,

  "temperature": 0.3,
  "top_p": 1.0,

  "allow_chat": true,
  "persist_conversation": true,
  "persist_user_history": true,
  "allow_guest": false,

  "disabled": false,

  "tools": [
    "crm.create_lead",
    "crm.get_recent_leads"
  ],

  "mcp_servers": [
    "gmail"
  ],

  "knowledge": [
    {
      "source": "crm_sales_playbook",
      "mode": "mandatory",
      "priority": 1,
      "max_chunks": 5,
      "token_budget": 2000
    }
  ],

  "context_strategy": "Summarize",
  "history_limit": 20,
  "max_turns": 20,
  "max_knowledge_tokens": 4000,

  "tts_model": null,
  "tts_voice": null,
  "image_generation_model": null,

  "enable_prompt_caching": false,
  "enable_conversation_data": false,
  "autonaming_of_conversation_title": true,

  "version": "1.0"
}
```

### 6.2 Field Reference

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `type` | string | **Yes** | &mdash; | Must be `"agent"`. |
| `agent_name` | string | **Yes** | &mdash; | Unique agent name. Used as the DocType primary key. |
| `description` | string | No | `""` | Human-readable description. |
| `provider` | string | **Yes** | &mdash; | Name of an `AI Provider` document (e.g. `"openai"`). |
| `model` | string | **Yes** | &mdash; | Name of an `AI Model` document (e.g. `"gpt-4o-mini"`). |
| `prompt_mode` | string | No | `"Local"` | `"Local"` (inline instructions) or `"Template"` (link to Agent Prompt). |
| `instructions` | string | No | `""` | System prompt text. Used when `prompt_mode` is `"Local"`. |
| `agent_prompt` | string | No | `null` | Name of an `Agent Prompt` document. Used when `prompt_mode` is `"Template"`. Can be a reference to a prompt defined in the same app (e.g. `"crm.lead_agent_prompt"` resolved via the `prompts/` folder). |
| `temperature` | float | No | `1.0` | LLM temperature (0.0&ndash;2.0). |
| `top_p` | float | No | `1.0` | Nucleus sampling parameter. |
| `allow_chat` | bool | No | `false` | Enable the chat UI for this agent. |
| `persist_conversation` | bool | No | `true` | Maintain conversation history across runs. |
| `persist_user_history` | bool | No | `true` | Per-user conversation history for Doc Event / Schedule triggers. |
| `allow_guest` | bool | No | `false` | Allow guest (unauthenticated) users to interact. |
| `disabled` | bool | No | `false` | If `true`, agent is imported but disabled. |
| `tools` | array&lt;string&gt; | No | `[]` | List of tool names. Each must match an `Agent Tool Function` document name (either pre-existing or defined in the same or another app's `tools/` folder). |
| `mcp_servers` | array&lt;string&gt; | No | `[]` | List of MCP Server names to link. |
| `knowledge` | array&lt;object&gt; | No | `[]` | Knowledge source bindings. See section 6.3. |
| `context_strategy` | string | No | `"Summarize"` | `"Summarize"`, `"FIFO"`, or `"None"`. |
| `history_limit` | int | No | `20` | Max conversation messages to retain in context. |
| `max_turns` | int | No | `20` | Max tool-call rounds per run. |
| `max_knowledge_tokens` | int | No | `4000` | Token budget for knowledge injection. |
| `tts_model` | string | No | `null` | Name of an `AI Model` for text-to-speech. |
| `tts_voice` | string | No | `null` | Voice identifier for TTS. |
| `image_generation_model` | string | No | `null` | Name of an `AI Model` for image generation. |
| `enable_prompt_caching` | bool | No | `false` | Enable prompt caching (provider-dependent). |
| `enable_conversation_data` | bool | No | `false` | Give agent access to conversation data tools. |
| `autonaming_of_conversation_title` | bool | No | `true` | Auto-generate conversation titles. |
| `version` | string | No | `"1.0"` | Definition version for future migration support. |

### 6.3 Knowledge Binding Object

Each entry in the `knowledge` array maps to an `Agent Knowledge` child table row:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `source` | string | **Yes** | &mdash; | Name of a `Knowledge Source` document. |
| `mode` | string | No | `"optional"` | `"mandatory"` (auto-injected) or `"optional"` (tool-based). |
| `priority` | int | No | `0` | Retrieval priority (higher = first). |
| `max_chunks` | int | No | `5` | Max chunks to retrieve per query. |
| `token_budget` | int | No | `2000` | Max tokens for this source in mandatory mode. |

### 6.4 Template Prompt Reference

When `prompt_mode` is `"Template"`, the `agent_prompt` field references a prompt by its
slug. If the prompt is defined in the same app's `prompts/` folder, use the dotted
reference format:

```json
{
  "type": "agent",
  "agent_name": "CRM Lead Assistant",
  "prompt_mode": "Template",
  "agent_prompt": "lead_agent_prompt",
  "..."
}
```

The discovery engine resolves the slug to the imported `Agent Prompt` document name
during the agent import phase (which runs after prompts are imported).

---

## 7. Prompt Definition Schema

**Target DocType:** Agent Prompt

**File location:** `<app>/huf/prompts/<name>.prompt.json`

### 7.1 Full Schema

```json
{
  "type": "prompt",

  "title": "Lead Management Instructions",
  "slug": "lead_agent_prompt",

  "description": "System prompt for the CRM lead management agent",

  "category": null,
  "visibility": "App",
  "tags": "crm, leads, sales",

  "prompt_body": "You are a CRM assistant specialising in lead management.\n\nYour responsibilities:\n- Help sales reps qualify leads\n- Suggest next actions for each lead\n- Summarise lead activity history\n\nAlways be professional and concise.",

  "is_active": true,

  "version": "1.0"
}
```

### 7.2 Field Reference

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `type` | string | **Yes** | &mdash; | Must be `"prompt"`. |
| `title` | string | **Yes** | &mdash; | Human-readable title. |
| `slug` | string | **Yes** | &mdash; | URL-friendly unique identifier. Used for cross-references from agent definitions. |
| `description` | string | No | `""` | Description of the prompt's purpose. |
| `category` | string | No | `null` | Name of an `Agent Prompt Category` document. |
| `visibility` | string | No | `"App"` | `"Public"`, `"App"`, or `"Private"`. Definitions from apps default to `"App"`. |
| `tags` | string | No | `""` | Comma-separated tags for filtering. |
| `prompt_body` | string | **Yes** | &mdash; | The prompt template content. Supports multi-line text. |
| `is_active` | bool | No | `true` | Whether the prompt is active and available for use. |
| `version` | string | No | `"1.0"` | Definition version. |

### 7.3 Future Fields (Reserved)

These fields are reserved for future use and will be ignored if present:

| Field | Purpose |
|-------|---------|
| `variables` | Template variable declarations for dynamic prompts |
| `prompt_type` | Classification (system, user, few-shot, etc.) |
| `template_engine` | Template rendering engine (jinja, mustache, etc.) |

---

## 8. Tool Definition Schema

**Target DocType:** Agent Tool Function

**File location:** `<app>/huf/tools/<name>.tool.json`

### 8.1 Full Schema

```json
{
  "type": "tool",

  "tool_name": "crm.create_lead",
  "description": "Create a new CRM Lead with the given details",

  "tool_type": "App Provided",
  "types": "Custom Function",

  "function_path": "crm.api.leads.create_lead",

  "reference_doctype": "Lead",

  "parameters": [
    {
      "label": "Lead Name",
      "fieldname": "lead_name",
      "type": "string",
      "required": true,
      "description": "Full name of the lead"
    },
    {
      "label": "Email",
      "fieldname": "email",
      "type": "string",
      "required": false,
      "description": "Email address of the lead"
    },
    {
      "label": "Company",
      "fieldname": "company",
      "type": "string",
      "required": false,
      "description": "Company name"
    },
    {
      "label": "Source",
      "fieldname": "source",
      "type": "string",
      "required": false,
      "description": "Lead source (e.g. Website, Referral, Campaign)",
      "options": "Website\nReferral\nCampaign\nOther"
    }
  ],

  "base_url": null,
  "http_headers": [],

  "pass_parameters_as_json": false,
  "is_read_only": false,
  "allowed_for_guest": false,
  "required_permission": "create",

  "version": "1.0"
}
```

### 8.2 Field Reference

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `type` | string | **Yes** | &mdash; | Must be `"tool"`. |
| `tool_name` | string | **Yes** | &mdash; | Unique tool name. Convention: `<app>.<action>` (e.g. `crm.create_lead`). |
| `description` | string | **Yes** | &mdash; | Clear description of what the tool does. The LLM reads this to decide when to use the tool. |
| `tool_type` | string | No | `"App Provided"` | Name of an `Agent Tool Type` document. Defaults to `"App Provided"` for file-discovered tools. |
| `types` | string | No | `"App Provided"` | The function type. One of: `Custom Function`, `App Provided`, `Get Document`, `Get List`, `Create Document`, `Update Document`, `Delete Document`, `Submit Document`, `Cancel Document`, `GET`, `POST`, `Run Agent`, or any other value from the Agent Tool Function `types` select field. For file-based tools with a `function_path`, use `"Custom Function"` or `"App Provided"`. |
| `function_path` | string | Conditional | &mdash; | Dotted Python path to the callable (e.g. `crm.api.leads.create_lead`). **Required** when `types` is `"Custom Function"` or `"App Provided"`. |
| `reference_doctype` | string | No | `null` | Target DocType for CRUD-type tools (e.g. `"Lead"`). |
| `parameters` | array&lt;object&gt; | No | `[]` | Parameter definitions. See section 8.3. |
| `base_url` | string | No | `null` | Base URL prefix for HTTP-type tools (`GET`, `POST`). |
| `http_headers` | array&lt;object&gt; | No | `[]` | Custom HTTP headers. Each object has `key` and `value` string fields. |
| `pass_parameters_as_json` | bool | No | `false` | Pass all parameters as a single JSON string argument. |
| `is_read_only` | bool | No | `false` | Restrict this tool to read-only operations. |
| `allowed_for_guest` | bool | No | `false` | Allow guest users to invoke this tool. |
| `required_permission` | string | No | `null` | Required Frappe permission type: `read`, `write`, `create`, `delete`, `submit`, `cancel`. |
| `agent` | string | No | `null` | Target agent name (for `Run Agent` type tools). |
| `version` | string | No | `"1.0"` | Definition version. |

### 8.3 Parameter Object

Each entry in the `parameters` array maps to an `Agent Function Params` child table row:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `label` | string | **Yes** | &mdash; | Human-readable parameter label. |
| `fieldname` | string | **Yes** | &mdash; | Parameter name (used as the function argument name). |
| `type` | string | **Yes** | &mdash; | Data type: `string`, `integer`, `number`, `float`, `boolean`, `object`, `array`. |
| `required` | bool | No | `false` | Whether the parameter is required. |
| `description` | string | No | `""` | Description shown to the LLM to explain the parameter's purpose. |
| `options` | string | No | `null` | Newline-separated list of allowed values (for enum-like parameters). |

### 8.4 HTTP Header Object

For HTTP-type tools (`GET`, `POST`):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `key` | string | **Yes** | HTTP header name (e.g. `Authorization`). |
| `value` | string | **Yes** | HTTP header value (e.g. `Bearer {{api_key}}`). |

### 8.5 Compatibility with Existing `huf_tools` Hook

The file-based tool discovery system is a **superset** of the existing `huf_tools` hook
mechanism. Tools can be declared via either method:

| Method | Schema | Discovery |
|--------|--------|-----------|
| `huf_tools` hook in `hooks.py` | Minimal: `tool_name`, `description`, `function_path`, `parameters` | Via `frappe.get_hooks("huf_tools")` |
| `huf/tools/*.tool.json` files | Full: all fields from section 8.2 | Via filesystem scan |

Both methods result in `Agent Tool Function` documents with `types` set to
`"App Provided"`. The file-based method supports the full field set while the hook-based
method uses a minimal schema for backward compatibility.

If the same `tool_name` is declared via both methods, the **file-based definition takes
precedence** (it is processed after hook-based tools).

---

## 9. Provider Definition Schema

**Target DocType:** AI Provider

**File location:** `<app>/huf/providers/<name>.provider.json`

> **Note:** Provider definitions are optional and typically unnecessary. Most apps will
> reference providers that already exist in the target HUF installation. Provider
> definitions are useful for declaring that a provider *should* exist, allowing the sync
> engine to create a placeholder if it is missing.

### 9.1 Full Schema

```json
{
  "type": "provider",

  "provider_name": "openai",

  "is_local_llm": false,
  "url": null,
  "port": null,

  "version": "1.0"
}
```

### 9.2 Field Reference

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `type` | string | **Yes** | &mdash; | Must be `"provider"`. |
| `provider_name` | string | **Yes** | &mdash; | Provider name (e.g. `"openai"`, `"anthropic"`, `"google"`). |
| `is_local_llm` | bool | No | `false` | Whether this is a local/self-hosted LLM provider. |
| `url` | string | No | `null` | Base URL for local LLM providers. |
| `port` | int | No | `null` | Port for local LLM providers. |
| `version` | string | No | `"1.0"` | Definition version. |

### 9.3 Important: API Keys

**API keys are never stored in definition files.** The `api_key` field of the `AI
Provider` DocType uses Frappe's encrypted `Password` field type and must be configured
by the site administrator through the HUF UI or Frappe Desk after the provider
document is created.

If a provider definition references a `provider_name` that already exists, the existing
document is left unchanged (no fields are overwritten). This prevents file-based
definitions from clearing manually-configured API keys.

---

## 10. Model Definition Schema

**Target DocType:** AI Model

**File location:** `<app>/huf/models/<name>.model.json`

### 10.1 Full Schema

```json
{
  "type": "model",

  "model_name": "gpt-4o-mini",
  "provider": "openai",

  "version": "1.0"
}
```

### 10.2 Field Reference

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `type` | string | **Yes** | &mdash; | Must be `"model"`. |
| `model_name` | string | **Yes** | &mdash; | Model name. Can be user-friendly (e.g. `"gpt-4o-mini"`) or LiteLLM format (e.g. `"openai/gpt-4o-mini"`). |
| `provider` | string | **Yes** | &mdash; | Name of the `AI Provider` this model belongs to. |
| `version` | string | No | `"1.0"` | Definition version. |

---

## 11. Knowledge Definition Schema

**Target DocType:** Knowledge Source

**File location:** `<app>/huf/knowledge/<name>.knowledge.json`

### 11.1 Full Schema

```json
{
  "type": "knowledge",

  "source_name": "crm_sales_playbook",
  "description": "Sales guidelines, playbooks, and best practices for the CRM team",

  "knowledge_type": "sqlite_fts",
  "scope": "Global",
  "storage_mode": "Frappe File",

  "chunk_size": 512,
  "chunk_overlap": 50,

  "disabled": false,

  "version": "1.0"
}
```

### 11.2 Field Reference

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `type` | string | **Yes** | &mdash; | Must be `"knowledge"`. |
| `source_name` | string | **Yes** | &mdash; | Unique knowledge source name. |
| `description` | string | No | `""` | Human-readable description. |
| `knowledge_type` | string | No | `"sqlite_fts"` | Backend type: `"sqlite_fts"` or `"sqlite_vec"`. |
| `scope` | string | No | `"Global"` | `"Site"`, `"Workspace"`, `"Agent"`, or `"Global"`. |
| `storage_mode` | string | No | `"Frappe File"` | Storage mode for indexed data. |
| `chunk_size` | int | No | `512` | Number of characters per chunk. |
| `chunk_overlap` | int | No | `50` | Overlap between adjacent chunks. |
| `disabled` | bool | No | `false` | Whether the knowledge source is disabled. |
| `embedding_model` | string | No | `null` | Embedding model name (for `sqlite_vec` type). |
| `vector_dimension` | int | No | `1536` | Vector dimension (for `sqlite_vec` type). |
| `embedding_provider` | string | No | `null` | AI Provider for embeddings (for `sqlite_vec` type). |
| `version` | string | No | `"1.0"` | Definition version. |

### 11.3 Important: Knowledge Content

The knowledge definition file only creates the **Knowledge Source container**. Actual
content (files, text, URLs) must be added as **Knowledge Input** documents after the
source is created, either through the HUF UI or programmatically.

A future extension may support bundling content files alongside the knowledge definition
(see section 33).

---

## 12. Trigger Definition Schema

**Target DocType:** Agent Trigger

**File location:** `<app>/huf/triggers/<name>.trigger.json`

### 12.1 Full Schema (Doc Event Example)

```json
{
  "type": "trigger",

  "trigger_name": "crm_lead_after_insert",
  "agent": "CRM Lead Assistant",

  "trigger_type": "Doc Event",

  "reference_doctype": "Lead",
  "doc_event": "after_insert",
  "condition": "doc.source == 'Website'",

  "disabled": false,

  "version": "1.0"
}
```

### 12.2 Full Schema (Schedule Example)

```json
{
  "type": "trigger",

  "trigger_name": "daily_lead_summary",
  "agent": "CRM Lead Assistant",

  "trigger_type": "Schedule",

  "scheduled_interval": "Daily",
  "interval_count": 1,

  "disabled": false,

  "version": "1.0"
}
```

### 12.3 Full Schema (Webhook Example)

```json
{
  "type": "trigger",

  "trigger_name": "crm_webhook_trigger",
  "agent": "CRM Lead Assistant",

  "trigger_type": "Webhook",

  "webhook_slug": "crm-lead-hook",

  "disabled": false,

  "version": "1.0"
}
```

### 12.4 Field Reference

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `type` | string | **Yes** | &mdash; | Must be `"trigger"`. |
| `trigger_name` | string | **Yes** | &mdash; | Unique trigger name. |
| `agent` | string | **Yes** | &mdash; | Name of the `Agent` to execute. |
| `trigger_type` | string | **Yes** | &mdash; | `"Schedule"`, `"Doc Event"`, `"Webhook"`, `"App Event"`, or `"Manual"`. |
| `disabled` | bool | No | `false` | Whether the trigger is disabled. |
| `reference_doctype` | string | Conditional | `null` | Target DocType. **Required** when `trigger_type` is `"Doc Event"`. |
| `doc_event` | string | Conditional | `null` | Document event name. **Required** when `trigger_type` is `"Doc Event"`. Values: `before_insert`, `after_insert`, `validate`, `before_save`, `after_save`, `before_submit`, `after_submit`, `before_cancel`, `on_submit`, `on_update`, `before_rename`, `after_rename`, `on_trash`, `after_delete`. |
| `condition` | string | No | `null` | Python expression evaluated before triggering (Doc Event only). Has access to `doc` variable. |
| `scheduled_interval` | string | Conditional | `null` | **Required** when `trigger_type` is `"Schedule"`. Values: `Hourly`, `Daily`, `Weekly`, `Monthly`, `Yearly`. |
| `interval_count` | int | No | `1` | Number of intervals between executions. |
| `webhook_slug` | string | No | `null` | URL slug for webhook endpoint. |
| `webhook_key` | string | No | `null` | Authentication key for webhook. |
| `app_name` | string | No | `null` | App name for App Event triggers. |
| `event_name` | string | No | `null` | Event name for App Event triggers. |
| `metadata` | object | No | `null` | Additional trigger metadata (JSON object). |
| `version` | string | No | `"1.0"` | Definition version. |

---

## 13. File Naming Convention

### 13.1 Recommended Pattern

```
<descriptive_name>.<definition_type>.json
```

Examples:

```
agents/
  crm_lead_assistant.agent.json
  crm_deal_closer.agent.json

tools/
  create_lead.tool.json
  get_recent_leads.tool.json
  update_deal_stage.tool.json

prompts/
  lead_agent_prompt.prompt.json
  deal_summary.prompt.json

providers/
  openai.provider.json

models/
  gpt_4o_mini.model.json

knowledge/
  sales_playbook.knowledge.json

triggers/
  lead_after_insert.trigger.json
  daily_lead_summary.trigger.json
```

### 13.2 Rules

1. File names must end with `.json`.
2. The `.<definition_type>.json` suffix is **recommended** but not enforced. A file
   named `create_lead.json` in the `tools/` folder will be treated as a tool definition
   (the folder determines the type, not the filename suffix).
3. File names should use `snake_case` with no spaces.
4. The file name does not need to match the `name` / `tool_name` / `agent_name` field
   inside the JSON; the JSON field value is authoritative.
5. One definition per file. Files containing multiple definitions are not supported.

---

## 14. Envelope Format

### 14.1 Standard Format

Every definition file **must** include a `type` field at the top level:

```json
{
  "type": "<definition_type>",
  "...": "..."
}
```

Valid `type` values: `agent`, `tool`, `prompt`, `provider`, `model`, `knowledge`,
`trigger`.

### 14.2 Why a Flat Structure

The definition schema uses a **flat structure** (all fields at the top level) rather than
a nested envelope like `{ "type": "agent", "definition": { ... } }`. This design choice:

- Reduces nesting depth in JSON files.
- Makes files easier to read and edit.
- Maps directly to DocType field structures without unwrapping.

### 14.3 Validation

The `type` field is validated against:

1. The folder the file was found in (`agents/` folder expects `"type": "agent"`).
2. The set of known definition types.

If the `type` field does not match the expected type for the folder, a warning is logged
and the file is skipped.

---

## 15. Discovery Engine

### 15.1 Scanner

The scanner walks each app's `huf/` directory and collects definition file paths:

```python
def scan_app(app_name: str, huf_dir: str) -> dict[str, list[Path]]:
    """
    Scan an app's huf/ directory for definition files.

    Returns:
        dict mapping definition type to list of file paths.
        e.g. {"agents": [Path("...lead_assistant.agent.json")], "tools": [...]}
    """
    KNOWN_TYPES = {
        "agents", "tools", "prompts",
        "providers", "models", "knowledge", "triggers",
    }
    definitions = {}

    for type_dir in KNOWN_TYPES:
        type_path = os.path.join(huf_dir, type_dir)
        if not os.path.isdir(type_path):
            continue

        files = []
        for fname in sorted(os.listdir(type_path)):
            if fname.endswith(".json") and not fname.startswith("."):
                files.append(os.path.join(type_path, fname))

        if files:
            definitions[type_dir] = files

    return definitions
```

Key properties:

- Only scans known subdirectories; unknown folders are ignored.
- Files are sorted alphabetically for deterministic processing order.
- Hidden files (starting with `.`) are skipped.
- Only `.json` files are included.

### 15.2 Loader

The loader reads and parses each JSON file:

```python
def load_definition(file_path: str, expected_type: str) -> dict | None:
    """
    Load and parse a single definition file.

    Returns:
        Parsed definition dict, or None if the file is invalid.
    """
    try:
        with open(file_path, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        log_warning(f"Invalid JSON in {file_path}: {e}")
        return None

    if not isinstance(data, dict):
        log_warning(f"Expected JSON object in {file_path}, got {type(data).__name__}")
        return None

    file_type = data.get("type")
    # Map folder name to singular type
    type_mapping = {
        "agents": "agent", "tools": "tool", "prompts": "prompt",
        "providers": "provider", "models": "model",
        "knowledge": "knowledge", "triggers": "trigger",
    }
    if file_type != type_mapping.get(expected_type):
        log_warning(
            f"Type mismatch in {file_path}: "
            f"expected '{type_mapping.get(expected_type)}', got '{file_type}'"
        )
        return None

    return data
```

---

## 16. Import Pipeline

Each definition passes through a four-stage pipeline:

```
JSON File  →  Load  →  Validate  →  Normalise  →  Upsert DocType
```

### 16.1 Stage: Load

Read the file, parse JSON, verify the `type` field matches the folder.

### 16.2 Stage: Validate

Apply type-specific validation rules (see section 17).

### 16.3 Stage: Normalise

Transform the definition into a DocType-compatible payload:

- Map JSON field names to DocType field names.
- Resolve cross-references (tool names, provider names, prompt slugs).
- Apply defaults for missing optional fields.
- Convert child table arrays into Frappe child document format.

### 16.4 Stage: Upsert DocType

Create or update the target DocType document:

- **Key field** determines identity (e.g. `agent_name` for agents, `tool_name` for tools).
- If a document with the same key exists → **update** it.
- If no document exists → **insert** a new one.
- Set provenance fields (`source_app`, `source_file`) on the document.

---

## 17. Validation Layer

### 17.1 Common Validations (All Types)

| Check | Error Level | Description |
|-------|-------------|-------------|
| Valid JSON | Error (skip) | File must be parseable JSON. |
| Top-level object | Error (skip) | Root value must be a JSON object (`{}`), not array or primitive. |
| `type` field present | Error (skip) | Every definition must declare its type. |
| `type` matches folder | Error (skip) | `type` value must correspond to the folder it was found in. |
| Required fields present | Error (skip) | Type-specific required fields must exist and be non-empty. |
| Field types correct | Warning | String fields should be strings, numbers should be numbers, etc. Best-effort coercion is applied. |

### 17.2 Tool-Specific Validations

| Check | Error Level | Description |
|-------|-------------|-------------|
| `function_path` is importable | Error (skip) | The dotted path must resolve to an importable Python module. |
| Function is callable | Error (skip) | The resolved attribute must be callable. |
| `parameters` is a list | Error (skip) | Must be an array, not a single object or string. |
| Each parameter has `fieldname` and `type` | Warning | Missing fields default to empty string / `"string"`. |

### 17.3 Agent-Specific Validations

| Check | Error Level | Description |
|-------|-------------|-------------|
| Referenced `provider` exists | Warning | Provider must exist as an `AI Provider` document or be declared in a `providers/` folder. |
| Referenced `model` exists | Warning | Model must exist as an `AI Model` document or be declared in a `models/` folder. |
| Referenced `tools` exist | Warning | Each tool name must resolve to an `Agent Tool Function` document. Unresolvable tools are omitted from the agent's tool list. |
| Referenced `knowledge` sources exist | Warning | Each knowledge source must resolve. Unresolvable sources are omitted. |

### 17.4 Prompt-Specific Validations

| Check | Error Level | Description |
|-------|-------------|-------------|
| `slug` is unique | Warning | If another prompt with the same slug exists from a different source, the import is skipped and a warning is logged. |
| `prompt_body` is non-empty | Error (skip) | A prompt without content is not useful. |

### 17.5 Trigger-Specific Validations

| Check | Error Level | Description |
|-------|-------------|-------------|
| Referenced `agent` exists | Error (skip) | The target agent must exist. |
| `reference_doctype` valid for Doc Event | Error (skip) | The DocType must exist in the system. |
| `doc_event` is a valid event name | Warning | Must be one of the known Frappe document events. |

### 17.6 Circular Dependency Check

The validator checks for circular references:

- Agent A references tool "run_agent_B" which runs Agent B, which references tool
  "run_agent_A" which runs Agent A.

Circular chains are detected during the normalisation phase and logged as warnings.
The cycle-causing reference is omitted.

---

## 18. Upsert Strategy

### 18.1 Deterministic Keys

Each definition type uses a specific field as its primary key for upsert operations:

| Definition Type | Key Field | DocType Field |
|----------------|-----------|---------------|
| Agent | `agent_name` | `Agent.agent_name` |
| Tool | `tool_name` | `Agent Tool Function.tool_name` |
| Prompt | `slug` | `Agent Prompt.slug` |
| Provider | `provider_name` | `AI Provider.provider_name` |
| Model | `model_name` | `AI Model.model_name` |
| Knowledge | `source_name` | `Knowledge Source.source_name` |
| Trigger | `trigger_name` | `Agent Trigger.trigger_name` |

### 18.2 Upsert Logic

```python
def upsert_definition(doctype: str, key_field: str, key_value: str, payload: dict):
    existing = frappe.db.get_value(doctype, {key_field: key_value})

    if existing:
        doc = frappe.get_doc(doctype, existing)
        doc.update(payload)
        doc.save(ignore_permissions=True)
    else:
        payload["doctype"] = doctype
        frappe.get_doc(payload).insert(ignore_permissions=True)
```

### 18.3 Update Behaviour

When updating existing documents:

- **Regular fields** are overwritten with the file-based values.
- **Encrypted fields** (`api_key` on AI Provider) are **never** overwritten from file
  definitions. If a provider already exists, only non-sensitive fields are updated.
- **Read-only / auto-calculated fields** (`last_run`, `total_run`, `status`, etc.) are
  not modified.
- **Child tables** (tools, knowledge, parameters) are replaced entirely with the
  file-based values.

### 18.4 Orphan Handling

When a full scan is performed (not incremental), definitions that were previously
imported from an app but are no longer present in that app's `huf/` folder are
considered **orphaned**.

Orphan handling strategy:

1. After scanning, compare imported definitions against the current file set.
2. Definitions whose `source_file` no longer exists are flagged.
3. Orphaned definitions are **not deleted automatically** to prevent data loss.
4. Instead, they are logged and can be cleaned up via the "Rebuild Definitions" action
   in the sync UI.

---

## 19. Dependency Resolution

### 19.1 Load Order

Definitions are imported in a strict order to satisfy dependencies:

```
Phase 1:  providers      (no dependencies)
Phase 2:  models         (depends on: providers)
Phase 3:  prompts        (no dependencies)
Phase 4:  tools          (no dependencies for definition; function_path validated)
Phase 5:  knowledge      (no dependencies)
Phase 6:  triggers       (depends on: agents)
Phase 7:  agents         (depends on: providers, models, tools, knowledge, prompts)
```

**Agents are always imported last** because they reference providers, models, tools,
knowledge sources, and prompts.

**Triggers are imported after agents** because each trigger references an agent.

### 19.2 Cross-App Dependencies

An agent in app A can reference a tool defined in app B:

```json
{
  "type": "agent",
  "agent_name": "HR Onboarding Bot",
  "tools": [
    "hrms.create_employee",
    "crm.get_contact"
  ]
}
```

This works because:

1. All apps are scanned and their tools are imported in Phase 4.
2. Agents are imported in Phase 7, after all tools from all apps exist.

If a referenced tool does not exist (because the declaring app is not installed), the
reference is logged as a warning and omitted from the agent's tool list.

### 19.3 Intra-App Dependencies

Within a single app, the load order ensures that an agent can reference prompts, tools,
and knowledge sources defined in the same app's `huf/` folder:

```
crm/huf/
  prompts/lead_prompt.prompt.json        # Imported in Phase 3
  tools/create_lead.tool.json            # Imported in Phase 4
  knowledge/playbook.knowledge.json      # Imported in Phase 5
  agents/lead_assistant.agent.json       # Imported in Phase 7 (references all above)
```

---

## 20. App Isolation and Provenance

### 20.1 Provenance Fields

Every imported definition should store its origin:

| Field | Type | Description |
|-------|------|-------------|
| `source_app` | Data | The Frappe app that provided this definition (e.g. `"crm"`). |
| `source_file` | Data | Relative path to the source file (e.g. `"crm/huf/agents/lead_assistant.agent.json"`). |

These fields are set during import and used for:

- **Updates**: Knowing which file to re-read when syncing.
- **Orphan detection**: Identifying definitions whose source file has been removed.
- **Re-sync**: Selectively re-importing definitions from a specific app.
- **UI display**: Showing the source app in the HUF interface.

### 20.2 DocType Field Additions

The following fields should be added to each target DocType:

```python
# Added to Agent, Agent Tool Function, Agent Prompt,
# AI Provider, AI Model, Knowledge Source, Agent Trigger

{
    "fieldname": "source_app",
    "fieldtype": "Data",
    "label": "Source App",
    "read_only": 1,
    "hidden": 1,
    "description": "App that provided this definition via file-based discovery"
},
{
    "fieldname": "source_file",
    "fieldtype": "Data",
    "label": "Source File",
    "read_only": 1,
    "hidden": 1,
    "description": "Relative path to the source definition file"
}
```

### 20.3 Distinguishing Sources

Definitions can come from three sources:

| Source | `source_app` | `source_file` |
|--------|-------------|---------------|
| Created in HUF UI | `null` | `null` |
| File-based discovery | `"crm"` | `"crm/huf/tools/create_lead.tool.json"` |
| `huf_tools` hook (legacy) | `"crm"` (via `provider_app`) | `null` |

---

## 21. Sync Algorithm

### 21.1 Full Sync (after_migrate, after_install, manual)

```
discover_all_apps()
    │
    ├── for each installed app:
    │     ├── locate <app>/huf/ directory
    │     ├── scan all type subdirectories
    │     └── collect file paths by type
    │
    ├── Phase 1: Load and import providers from all apps
    ├── Phase 2: Load and import models from all apps
    ├── Phase 3: Load and import prompts from all apps
    ├── Phase 4: Load and import tools from all apps
    ├── Phase 5: Load and import knowledge from all apps
    ├── Phase 6: Load and import agents from all apps
    ├── Phase 7: Load and import triggers from all apps
    │
    ├── Detect orphaned definitions
    ├── Log orphan warnings
    │
    └── Return sync summary
```

### 21.2 Incremental Sync (per-app)

```
sync_app_definitions(app_name)
    │
    ├── Locate <app>/huf/ directory
    ├── Scan all type subdirectories
    ├── Collect file paths by type
    │
    ├── Import definitions in dependency order
    │   (same phase order as full sync, but only for this app)
    │
    └── Return sync summary
```

### 21.3 Interaction with Existing Tool Sync

The new file-based discovery system coexists with the existing `huf_tools` hook-based
tool sync (`sync_discovered_tools` in `tool_registry.py`):

```
after_migrate
    │
    ├── Existing: sync_discovered_tools()    # Hook-based tools
    └── New:      discover_app_definitions() # File-based definitions (all types)
```

Both run during `after_migrate`. The file-based system processes tools after the
hook-based system, so file-based definitions take precedence for tools with the same
`tool_name`.

---

## 22. UI Export Feature

### 22.1 Export Capability

The HUF UI should allow exporting any definition to the JSON file format:

| Action | Input | Output |
|--------|-------|--------|
| Export Agent | Agent document | `<agent_name>.agent.json` |
| Export Tool | Agent Tool Function document | `<tool_name>.tool.json` |
| Export Prompt | Agent Prompt document | `<slug>.prompt.json` |
| Export Provider | AI Provider document | `<provider_name>.provider.json` |
| Export Model | AI Model document | `<model_name>.model.json` |
| Export Knowledge | Knowledge Source document | `<source_name>.knowledge.json` |
| Export Trigger | Agent Trigger document | `<trigger_name>.trigger.json` |

### 22.2 Export API

```python
@frappe.whitelist()
def export_definition(doctype: str, name: str) -> dict:
    """
    Export a HUF DocType document as a JSON definition.

    Args:
        doctype: The DocType name (e.g. "Agent", "Agent Tool Function")
        name: The document name

    Returns:
        dict with "filename" and "content" (JSON string)
    """
```

### 22.3 Bulk Export

Export an entire agent and its dependencies as a complete `huf/` folder structure:

```python
@frappe.whitelist()
def export_agent_bundle(agent_name: str) -> dict:
    """
    Export an agent with all its referenced tools, prompts, knowledge sources,
    and triggers as a complete huf/ folder bundle.

    Returns:
        dict mapping file paths to JSON content.
        e.g. {
            "agents/crm_lead_assistant.agent.json": "{...}",
            "tools/create_lead.tool.json": "{...}",
            "prompts/lead_prompt.prompt.json": "{...}",
        }
    """
```

### 22.4 Export Example

An agent created in the HUF UI can be exported for inclusion in an app:

```
UI: Agent "CRM Lead Assistant"
    ↓ Export
crm/huf/agents/crm_lead_assistant.agent.json
crm/huf/tools/create_lead.tool.json
crm/huf/tools/get_recent_leads.tool.json
crm/huf/prompts/lead_agent_prompt.prompt.json
```

---

## 23. Versioning Strategy

### 23.1 Definition Version Field

Every definition file includes an optional `version` field:

```json
{
  "type": "agent",
  "agent_name": "CRM Lead Assistant",
  "version": "1.0",
  "..."
}
```

### 23.2 Current Behaviour (v1)

In the initial implementation:

- The `version` field is stored but not used for migration logic.
- All definitions are treated as the latest version.
- Re-importing a definition with the same key overwrites the existing document.

### 23.3 Future Behaviour (Planned)

In future versions:

| Feature | Description |
|---------|-------------|
| Version comparison | Compare file version against imported version; skip if identical. |
| Migration scripts | Type-specific migration logic for schema changes between versions. |
| Breaking change detection | Warn when a new version removes fields or changes semantics. |
| Rollback | Ability to revert to a previous definition version. |

---

## 24. Failure Handling

### 24.1 Core Principle

**Discovery errors must never break app installation or migration.**

A malformed JSON file, a missing function path, or an invalid reference should log a
warning and skip the offending definition, not raise an exception that aborts
`bench migrate`.

### 24.2 Error Handling Strategy

```python
def import_definition(file_path, definition_type, app_name):
    try:
        data = load_definition(file_path, definition_type)
        if data is None:
            return  # Already logged

        validate(data, definition_type)
        payload = normalise(data, definition_type, app_name)
        upsert(payload, definition_type)

    except Exception as e:
        frappe.log_error(
            title="HUF App Discovery Error",
            message=f"Failed to import {file_path} from {app_name}: {e}"
        )
        # Continue with next file — do not re-raise
```

### 24.3 Error Levels

| Level | Behaviour | Example |
|-------|-----------|---------|
| **Error (skip)** | Definition is skipped entirely | Invalid JSON, missing required field, type mismatch |
| **Warning** | Definition is imported with degraded data | Missing optional reference, unknown field |
| **Info** | Logged for auditing | Successful import, no-op update (definition unchanged) |

### 24.4 Error Reporting

After a sync cycle completes, a summary is returned:

```python
{
    "synced_apps": ["crm", "hrms"],
    "total_definitions": 12,
    "by_type": {
        "agents": 3,
        "tools": 5,
        "prompts": 2,
        "knowledge": 1,
        "triggers": 1,
    },
    "errors": [
        "crm: tools/bad_tool.tool.json: function_path 'crm.api.nonexistent' is not importable",
        "hrms: agents/broken.agent.json: Invalid JSON at line 15"
    ],
    "error_count": 2,
    "warnings": [
        "crm: agents/lead_assistant.agent.json: referenced tool 'crm.old_tool' not found, skipped"
    ],
    "warning_count": 1
}
```

---

## 25. Manual Sync UI

### 25.1 Location

A dedicated page in the HUF frontend:

```
HUF → App Integrations (or Settings → App Definitions)
```

### 25.2 Features

| Element | Description |
|---------|-------------|
| **App list** | Table showing all installed apps with their `huf/` folder status (present / absent). |
| **Definition count** | Per-app count of discovered definitions by type. |
| **Last sync** | Timestamp of last successful sync per app. |
| **Sync All** button | Runs `discover_app_definitions()` for all apps. |
| **Sync App** button | Runs sync for a selected app only. |
| **Rebuild** button | Clears cached state and performs a full re-scan and re-import. |
| **View Source Files** | Expandable panel showing the file paths discovered for each app. |
| **Error log** | Displays recent sync errors from the Error Log. |

### 25.3 API Endpoints

```python
@frappe.whitelist()
def get_app_discovery_status():
    """
    Returns discovery status for all installed apps.

    Returns list of:
    {
        "app": "crm",
        "has_huf_dir": true,
        "definition_counts": {"agents": 2, "tools": 3, ...},
        "last_sync": "2026-03-07T14:30:00",
        "files": ["crm/huf/agents/lead_assistant.agent.json", ...]
    }
    """

@frappe.whitelist()
def discover_app_definitions(app_name=None):
    """Run discovery sync. See section 3.4."""

@frappe.whitelist()
def rebuild_app_definitions():
    """Clear all provenance data and re-import everything from scratch."""
```

---

## 26. Caching

### 26.1 Cache Key

```
huf:app_definitions:{app_name}
```

Stores the last scan timestamp and a hash of all definition files for the app.

### 26.2 Cache Storage

Cache is stored in the `Agent Settings` singleton document (consistent with the existing
tool registry cache pattern):

```python
{
    "last_definition_scans": {
        "crm": {
            "timestamp": "2026-03-07T14:30:00",
            "file_hash": "a1b2c3d4..."
        },
        "hrms": {
            "timestamp": "2026-03-07T14:30:00",
            "file_hash": "e5f6g7h8..."
        }
    }
}
```

### 26.3 Cache Invalidation

The cache is invalidated when:

| Event | Invalidation Scope |
|-------|-------------------|
| `bench migrate` runs | All apps (full re-scan) |
| App is installed or updated | Specific app |
| Manual "Sync" button clicked | Specific app or all apps |
| "Rebuild" button clicked | All apps (cache cleared entirely) |

### 26.4 File Change Detection

To determine if an app's definitions have changed without reading every file:

1. Compute a combined hash of all `*.json` file paths and their modification times in
   the app's `huf/` directory.
2. Compare against the stored `file_hash`.
3. If different, perform a full scan of that app. If identical, skip.

This is more accurate than the existing tool registry approach (which uses `hooks.py`
mtime as a proxy) because it directly monitors the definition files.

---

## 27. Security

### 27.1 Function Path Validation

For tool definitions with `function_path`, the discovery engine validates that:

1. The module is importable: `importlib.import_module(module_path)` succeeds.
2. The function exists: `getattr(module, function_name)` returns a value.
3. The function is callable: `callable(func)` is `True`.

```python
def validate_function_path(function_path: str) -> bool:
    """
    Validate that a dotted function path resolves to a callable.

    Uses frappe.get_attr() which applies Frappe's own security checks.
    """
    try:
        func = frappe.get_attr(function_path)
        return callable(func)
    except Exception:
        return False
```

### 27.2 No Secrets in Definition Files

Definition files must **never** contain:

- API keys or passwords
- Authentication tokens
- Private encryption keys
- Database credentials

The discovery engine does not process or store any `Password`-type fields from
definition files. If an `api_key` field is present in a provider definition, it is
ignored with a warning.

### 27.3 Permission Model

Imported definitions follow the standard Frappe permission model:

- All definitions are created with `ignore_permissions=True` during sync (administrative
  operation).
- Runtime access to agents, tools, and other resources is governed by the standard
  DocType permission rules and the `PermissionAwareToolRegistry`.

### 27.4 Condition Expression Safety

Trigger definitions with `condition` fields (for Doc Event triggers) use the same
`safe_eval` mechanism as the existing Agent Trigger DocType. Arbitrary code execution
is not possible.

---

## 28. Implementation Modules

### 28.1 Recommended File Structure

```
huf/ai/app_registry/
    __init__.py
    discovery.py         # App scanning and orchestration
    loader.py            # File reading and JSON parsing
    validator.py         # Type-specific validation rules
    normaliser.py        # Payload normalisation and defaults
    importer.py          # DocType upsert logic
    exporter.py          # UI export to JSON files
    cache.py             # Cache management
```

### 28.2 Module Responsibilities

| Module | Responsibility |
|--------|---------------|
| `discovery.py` | Top-level orchestration. Iterates apps, calls scanner, coordinates the import pipeline. Exposes the public `discover_app_definitions()` API. |
| `loader.py` | Filesystem scanning (`scan_app`), JSON file reading (`load_definition`), type detection. |
| `validator.py` | Type-specific validation functions: `validate_agent()`, `validate_tool()`, `validate_prompt()`, etc. Returns a list of errors/warnings per definition. |
| `normaliser.py` | Transforms raw JSON data into DocType-compatible payloads. Applies defaults, resolves references, maps field names. |
| `importer.py` | DocType upsert operations. Handles create-or-update logic, provenance field setting, child table management. |
| `exporter.py` | Reverse operation: reads a DocType document and produces a JSON definition file. Handles both single-definition and bundle export. |
| `cache.py` | Cache read/write/invalidation using `Agent Settings` singleton. File hash computation for change detection. |

### 28.3 Integration Points

| Hook / Entry Point | Module Called |
|-------------------|-------------|
| `after_migrate` | `discovery.discover_app_definitions()` |
| `after_install` | `discovery.discover_app_definitions()` |
| Manual sync button | `discovery.discover_app_definitions(app_name=...)` |
| Export button | `exporter.export_definition(doctype, name)` |
| Bundle export | `exporter.export_agent_bundle(agent_name)` |

---

## 29. Relationship to Existing Tool Registry

### 29.1 Current System (`tool_registry.py`)

The existing tool discovery system uses the `huf_tools` hook in `hooks.py`:

```python
# In an app's hooks.py
huf_tools = [
    {
        "tool_name": "crm.create_lead",
        "description": "Create a CRM Lead",
        "function_path": "crm.api.create_lead",
        "parameters": [
            {"name": "lead_name", "type": "string", "required": True}
        ]
    }
]
```

This is synced via `sync_discovered_tools()` in `tool_registry.py`.

### 29.2 Coexistence Strategy

Both systems coexist and complement each other:

| Aspect | Hook-based (`huf_tools`) | File-based (`huf/tools/`) |
|--------|-------------------------|--------------------------|
| Schema | Minimal (4 fields) | Full (all Agent Tool Function fields) |
| Declaration location | `hooks.py` | `huf/tools/*.tool.json` |
| Scope | Tools only | All definition types |
| Precedence | Lower (processed first) | Higher (processed second) |
| Backward compatible | Yes (existing mechanism) | Yes (new mechanism, additive) |

### 29.3 Migration Path

Apps currently using the `huf_tools` hook can migrate to file-based definitions at their
own pace:

1. **Phase 1**: Continue using `huf_tools` &mdash; works as before.
2. **Phase 2**: Add `huf/tools/` JSON files alongside `huf_tools` &mdash; both work, files take precedence for duplicate names.
3. **Phase 3**: Remove `huf_tools` entries from `hooks.py` &mdash; file-based definitions are the sole source.

There is no deadline or requirement to migrate. The hook-based system remains supported
indefinitely.

---

## 30. Developer Experience

### 30.1 Getting Started

For an app developer who wants to add AI capabilities to their Frappe app:

**Step 1: Install HUF** (if not already installed)

```bash
bench get-app https://github.com/tridz-dev/huf
bench --site <sitename> install-app huf
```

**Step 2: Create the `huf/` directory** in your app

```bash
mkdir -p <app_name>/<app_name>/huf/agents
mkdir -p <app_name>/<app_name>/huf/tools
mkdir -p <app_name>/<app_name>/huf/prompts
```

**Step 3: Add definition files**

Create a tool definition:

```json
// <app_name>/<app_name>/huf/tools/my_tool.tool.json
{
  "type": "tool",
  "tool_name": "myapp.my_tool",
  "description": "Does something useful",
  "function_path": "myapp.api.my_tool_function",
  "parameters": [
    {
      "label": "Input",
      "fieldname": "input",
      "type": "string",
      "required": true,
      "description": "The input value"
    }
  ]
}
```

Create an agent definition:

```json
// <app_name>/<app_name>/huf/agents/my_agent.agent.json
{
  "type": "agent",
  "agent_name": "My App Assistant",
  "description": "Helps with my app tasks",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "instructions": "You are a helpful assistant for My App...",
  "tools": ["myapp.my_tool"],
  "allow_chat": true
}
```

**Step 4: Run migrate**

```bash
bench migrate
```

HUF automatically discovers and imports the definitions. The agent is now available in
the HUF chat interface.

### 30.2 No HUF? No Problem.

If HUF is not installed on the target site:

- The `huf/` folder is ignored by Frappe (it is not a recognized module directory).
- No import errors occur.
- No runtime overhead.
- The app functions normally without AI capabilities.

### 30.3 Optional: Declare HUF as Required

If your app is AI-native and requires HUF to function:

```python
# In your app's hooks.py
required_apps = ["huf"]
```

This uses Frappe's standard `required_apps` mechanism. `bench install-app myapp` will
fail with a clear error if HUF is not installed first.

### 30.4 Development Workflow

```
1. Edit JSON definition files in your app
2. Run: bench migrate
   (or click "Sync App Definitions" in HUF UI)
3. Definitions are imported/updated in HUF
4. Test agent in HUF chat UI
5. Iterate on definitions
6. Commit JSON files to version control
```

---

## 31. End-to-End Example

### 31.1 Scenario

A CRM app wants to add:

- A lead management agent
- Two tools (create lead, get recent leads)
- A prompt template for the agent
- A knowledge source for sales guidelines

### 31.2 File Structure

```
crm/
  crm/
    huf/
      agents/
        lead_assistant.agent.json
      tools/
        create_lead.tool.json
        get_recent_leads.tool.json
      prompts/
        lead_management.prompt.json
      knowledge/
        sales_playbook.knowledge.json
```

### 31.3 Definition Files

**`prompts/lead_management.prompt.json`**

```json
{
  "type": "prompt",
  "title": "Lead Management Instructions",
  "slug": "crm_lead_management",
  "description": "System prompt for the CRM lead management agent",
  "visibility": "App",
  "tags": "crm, leads, sales",
  "prompt_body": "You are a CRM assistant specialising in lead management.\n\nYour responsibilities:\n- Help sales reps qualify and manage leads\n- Create new leads when asked\n- Retrieve and summarise recent lead activity\n- Suggest next actions for each lead\n\nRules:\n- Always confirm before creating or modifying data\n- Be professional and concise\n- Use the available tools rather than making assumptions"
}
```

**`tools/create_lead.tool.json`**

```json
{
  "type": "tool",
  "tool_name": "crm.create_lead",
  "description": "Create a new CRM Lead with the specified details. Returns the created Lead document.",
  "function_path": "crm.api.leads.create_lead",
  "parameters": [
    {
      "label": "Lead Name",
      "fieldname": "lead_name",
      "type": "string",
      "required": true,
      "description": "Full name of the lead"
    },
    {
      "label": "Email",
      "fieldname": "email",
      "type": "string",
      "required": false,
      "description": "Email address"
    },
    {
      "label": "Company",
      "fieldname": "company",
      "type": "string",
      "required": false,
      "description": "Company name"
    },
    {
      "label": "Source",
      "fieldname": "source",
      "type": "string",
      "required": false,
      "description": "Lead source",
      "options": "Website\nReferral\nCampaign\nOther"
    }
  ],
  "required_permission": "create"
}
```

**`tools/get_recent_leads.tool.json`**

```json
{
  "type": "tool",
  "tool_name": "crm.get_recent_leads",
  "description": "Get the most recent leads with optional filtering. Returns a list of Lead documents.",
  "function_path": "crm.api.leads.get_recent_leads",
  "parameters": [
    {
      "label": "Limit",
      "fieldname": "limit",
      "type": "integer",
      "required": false,
      "description": "Maximum number of leads to return (default: 10)"
    },
    {
      "label": "Status",
      "fieldname": "status",
      "type": "string",
      "required": false,
      "description": "Filter by lead status",
      "options": "Open\nReplied\nConverted\nDo Not Contact"
    }
  ],
  "is_read_only": true,
  "required_permission": "read"
}
```

**`knowledge/sales_playbook.knowledge.json`**

```json
{
  "type": "knowledge",
  "source_name": "crm_sales_playbook",
  "description": "Sales guidelines, objection handling, and qualification criteria",
  "knowledge_type": "sqlite_fts",
  "scope": "Global",
  "chunk_size": 512,
  "chunk_overlap": 50
}
```

**`agents/lead_assistant.agent.json`**

```json
{
  "type": "agent",
  "agent_name": "CRM Lead Assistant",
  "description": "Helps sales reps manage and qualify leads",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "prompt_mode": "Template",
  "agent_prompt": "crm_lead_management",
  "temperature": 0.3,
  "top_p": 1.0,
  "allow_chat": true,
  "persist_conversation": true,
  "tools": [
    "crm.create_lead",
    "crm.get_recent_leads"
  ],
  "knowledge": [
    {
      "source": "crm_sales_playbook",
      "mode": "mandatory",
      "priority": 1,
      "token_budget": 2000
    }
  ]
}
```

### 31.4 What Happens on `bench migrate`

```
1. HUF scans installed apps for huf/ directories
2. Finds crm/crm/huf/ with agents/, tools/, prompts/, knowledge/ folders
3. Phase 3 (Prompts):
   - Imports crm_lead_management prompt → creates Agent Prompt document
4. Phase 4 (Tools):
   - Validates crm.api.leads.create_lead is callable → creates Agent Tool Function
   - Validates crm.api.leads.get_recent_leads is callable → creates Agent Tool Function
5. Phase 5 (Knowledge):
   - Creates Knowledge Source "crm_sales_playbook" (status: Pending)
6. Phase 7 (Agents):
   - Resolves prompt reference "crm_lead_management" → Agent Prompt document
   - Resolves tool references → Agent Tool Function documents
   - Resolves knowledge reference → Knowledge Source document
   - Creates Agent "CRM Lead Assistant" with all links
7. Sets source_app="crm" and source_file on all created documents
8. Logs: "Synced 5 definitions from app 'crm'"
```

The agent is now visible in the HUF UI, available for chat, and ready to use.

---

## 32. Required App Declaration

### 32.1 When to Use

If your app is **AI-native** and HUF is essential for its functionality, declare it as a
required app:

```python
# myapp/hooks.py
required_apps = ["huf"]
```

### 32.2 Behaviour

- `bench install-app myapp` will check for HUF and fail with a clear message if it is
  not installed.
- This is standard Frappe behaviour, not a HUF-specific feature.

### 32.3 When NOT to Use

If AI capabilities are an **optional enhancement** (the app works fine without them),
do **not** declare HUF as required. The `huf/` folder will simply be ignored when HUF
is not installed.

---

## 33. Future Extensions

### 33.1 Additional Definition Types

The folder-based architecture is designed to be extended. Potential future definition
types:

| Folder | Purpose | Status |
|--------|---------|--------|
| `flows/` | Flow Definition JSON files for visual workflow builder | Planned |
| `guardrails/` | Input/output validation rules for agents | Planned |
| `skills/` | Reusable skill bundles (agent + tools + prompt as a unit) | Concept |
| `memory/` | Long-term memory configuration for agents | Concept |
| `policies/` | Access control and usage policies | Concept |
| `workflows/` | Frappe Workflow integration definitions | Concept |

### 33.2 Knowledge Content Bundling

Future versions may support bundling content files alongside knowledge definitions:

```
crm/huf/knowledge/
  sales_playbook.knowledge.json
  sales_playbook/
    chapter_1.md
    chapter_2.md
    faq.pdf
```

The knowledge definition would reference these files, and the discovery engine would
automatically create Knowledge Input documents and trigger indexing.

### 33.3 Definition Dependencies

Formal dependency declarations between definitions:

```json
{
  "type": "agent",
  "agent_name": "My Agent",
  "requires": {
    "tools": ["crm.create_lead >= 1.0"],
    "knowledge": ["sales_playbook"],
    "providers": ["openai"]
  }
}
```

### 33.4 Definition Testing

A test framework for validating definitions without a running Frappe site:

```bash
bench huf validate-definitions --app crm
```

### 33.5 Marketplace Integration

Definitions published to a central registry, discoverable and installable via:

```bash
bench huf install-agent crm-lead-assistant
```

---

## 34. Glossary

| Term | Definition |
|------|-----------|
| **Definition** | A JSON file describing a HUF resource (agent, tool, prompt, etc.). |
| **Definition type** | The category of a definition, corresponding to a HUF DocType (e.g. `agent`, `tool`). |
| **Discovery** | The process of scanning installed apps for `huf/` folders and collecting definition files. |
| **Sync** | The complete cycle of discovery, validation, normalisation, and upsert. |
| **Upsert** | Create-or-update operation: insert if new, update if existing. |
| **Provenance** | Metadata recording where a definition came from (`source_app`, `source_file`). |
| **Orphan** | A previously-imported definition whose source file no longer exists. |
| **Envelope** | The top-level JSON structure of a definition file, including the `type` field. |
| **Deterministic key** | The field used to identify a definition for upsert (e.g. `agent_name`, `tool_name`). |
| **Load order** | The sequence in which definition types are imported to satisfy dependencies. |

---

## 35. Summary

The HUF App Agent Discovery System enables:

- **Agent discovery** &mdash; external apps declare agents via JSON files.
- **Tool auto-registration** &mdash; tools are validated and synced into HUF
  automatically.
- **Prompt packaging** &mdash; reusable prompt templates travel with the app.
- **Knowledge source declaration** &mdash; RAG knowledge containers are created
  automatically.
- **Trigger configuration** &mdash; event-driven and scheduled triggers are set up
  without manual configuration.
- **Provider and model declarations** &mdash; ensure required AI infrastructure exists.

**Without:**

- Editing `hooks.py` (though the existing `huf_tools` hook remains supported).
- Manual configuration in the HUF UI.
- Tight coupling between the external app and HUF internals.

The system is designed to be **invisible when HUF is absent** and **automatic when HUF
is present**, following the same philosophy as Frappe's own DocType discovery mechanism.
