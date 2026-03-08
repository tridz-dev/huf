# HUF App Agent Discovery System

The App Agent Discovery system enables external Frappe apps to declare AI capabilities—agents, tools, prompts, providers, models, knowledge sources, and triggers—using plain JSON files in their repositories.

## Overview

When HUF is installed, it automatically:
1. Discovers definition files at well-known paths (`<app>/<app>/huf/`)
2. Validates and normalizes each definition
3. Syncs them into the corresponding HUF DocTypes
4. Makes them immediately usable by agents, flows, and the chat UI

When HUF is **not** installed, the `huf/` folder is inert and carries no runtime cost.

## Directory Structure

```
<app_name>/
  <app_name>/
    huf/
      agents/          # Agent definitions (*.agent.json)
      prompts/         # Prompt template definitions (*.prompt.json)
      tools/           # Tool definitions (*.tool.json)
      providers/       # AI Provider definitions (*.provider.json)
      models/          # AI Model definitions (*.model.json)
      knowledge/       # Knowledge Source definitions (*.knowledge.json)
      triggers/        # Agent Trigger definitions (*.trigger.json)
```

## Definition Types

### 1. Agent (`agents/*.agent.json`)

Full agent definitions with instructions, model, tools, and knowledge bindings.

```json
{
  "type": "agent",
  "agent_name": "CRM Lead Assistant",
  "description": "Helps sales reps manage and qualify leads",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "prompt_mode": "Local",
  "instructions": "You are a CRM assistant specialising in lead management...",
  "temperature": 0.3,
  "top_p": 1.0,
  "allow_chat": true,
  "persist_conversation": true,
  "tools": ["crm.create_lead", "crm.get_recent_leads"],
  "knowledge": [
    {
      "source": "crm_sales_playbook",
      "mode": "mandatory",
      "priority": 1,
      "max_chunks": 5,
      "token_budget": 2000
    }
  ],
  "version": "1.0"
}
```

**Key Fields:**
- `agent_name` (required): Unique agent identifier
- `provider` (required): Name of AI Provider document
- `model` (required): Name of AI Model document
- `prompt_mode`: `"Local"` (inline) or `"Template"` (reference to Agent Prompt)
- `instructions`: System prompt when `prompt_mode` is `"Local"`
- `tools`: List of tool names to attach
- `knowledge`: Array of knowledge source bindings
- `mcp_servers`: List of MCP Server names

### 2. Tool (`tools/*.tool.json`)

Tool definitions for Custom Function, App Provided, CRUD, or HTTP types.

```json
{
  "type": "tool",
  "tool_name": "crm.create_lead",
  "description": "Create a new CRM Lead with the specified details",
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
    }
  ],
  "required_permission": "create",
  "version": "1.0"
}
```

**Key Fields:**
- `tool_name` (required): Unique tool identifier (convention: `<app>.<action>`)
- `description` (required): Description for the LLM
- `types`: Tool type (Custom Function, App Provided, Get Document, Create Document, etc.)
- `function_path`: Python dotted path for Custom Function/App Provided types
- `parameters`: Array of parameter definitions
- `http_headers`: For HTTP-type tools

### 3. Prompt (`prompts/*.prompt.json`)

Reusable prompt templates with versioning.

```json
{
  "type": "prompt",
  "title": "Lead Management Instructions",
  "slug": "crm_lead_management",
  "description": "System prompt for the CRM lead management agent",
  "visibility": "App",
  "tags": "crm, leads, sales",
  "prompt_body": "You are a CRM assistant specialising in lead management...",
  "is_active": true,
  "version": "1.0"
}
```

**Key Fields:**
- `title` (required): Human-readable title
- `slug` (required): URL-friendly unique identifier
- `prompt_body` (required): The prompt template content
- `visibility`: `"Public"`, `"App"`, or `"Private"`
- `category`: Name of Agent Prompt Category

### 4. Provider (`providers/*.provider.json`)

AI service provider declarations (credentials added separately).

```json
{
  "type": "provider",
  "provider_name": "openai",
  "is_local_llm": false,
  "version": "1.0"
}
```

**Note:** API keys are never stored in definition files. They must be configured via the HUF UI after the provider document is created.

### 5. Model (`models/*.model.json`)

Model declarations linked to providers.

```json
{
  "type": "model",
  "model_name": "gpt-4o-mini",
  "provider": "openai",
  "version": "1.0"
}
```

### 6. Knowledge (`knowledge/*.knowledge.json`)

Knowledge source definitions for RAG.

```json
{
  "type": "knowledge",
  "source_name": "crm_sales_playbook",
  "description": "Sales guidelines and best practices",
  "knowledge_type": "sqlite_fts",
  "scope": "Global",
  "chunk_size": 512,
  "chunk_overlap": 50,
  "version": "1.0"
}
```

### 7. Trigger (`triggers/*.trigger.json`)

Event-driven, scheduled, or webhook triggers.

```json
{
  "type": "trigger",
  "trigger_name": "crm_lead_after_insert",
  "agent": "CRM Lead Assistant",
  "trigger_type": "Doc Event",
  "reference_doctype": "Lead",
  "doc_event": "after_insert",
  "condition": "doc.source == 'Website'",
  "version": "1.0"
}
```

**Trigger Types:**
- `Doc Event`: Fired on document lifecycle events
- `Schedule`: Time-based execution
- `Webhook`: HTTP endpoint trigger
- `App Event`: Application-level events
- `Manual`: Manually executed

## Usage

### Automatic Discovery

Discovery runs automatically on:
- `after_migrate`: After `bench migrate` completes
- `after_install`: After HUF itself is installed

### Manual Sync

```python
# Sync all apps
from huf.ai.app_registry import discover_app_definitions
result = discover_app_definitions()
print(f"Synced {result['total_definitions']} definitions from {result['synced_apps']}")

# Sync specific app
result = discover_app_definitions(app_name="crm")

# With caching (skip unchanged apps)
result = discover_app_definitions(use_cache=True)
```

### Check Discovery Status

```python
from huf.ai.app_registry import get_app_discovery_status
status = get_app_discovery_status()
for app_info in status:
    print(f"{app_info['app']}: {app_info['definition_counts']}")
```

### Rebuild All Definitions

```python
# Clear cache and re-import everything
from huf.ai.app_registry import rebuild_app_definitions
result = rebuild_app_definitions()
```

### Orphan Detection and Cleanup

Orphaned definitions are those previously imported but whose source files no longer exist:

```python
# Detect orphans
from huf.ai.app_registry.discovery import get_orphaned_definitions
orphans = get_orphaned_definitions(app_name="crm")

# Preview cleanup (dry run)
from huf.ai.app_registry.discovery import cleanup_orphaned_definitions
cleanup_result = cleanup_orphaned_definitions(app_name="crm", dry_run=True)

# Actually cleanup
from huf.ai.app_registry.discovery import cleanup_orphaned_definitions
cleanup_result = cleanup_orphaned_definitions(app_name="crm", dry_run=False)

# Auto-cleanup during discovery
from huf.ai.app_registry.discovery import discover_app_definitions_with_cleanup
result = discover_app_definitions_with_cleanup(cleanup_orphans=True)
```

### Export Definitions

Export from HUF UI back to JSON format:

```python
# Export single definition
from huf.ai.app_registry.exporter import export_definition
result = export_definition("Agent", "CRM Lead Assistant")
print(result["filename"])  # crm_lead_assistant.agent.json
print(result["content"])     # JSON content

# Export agent bundle (agent + tools + prompts + knowledge + triggers)
from huf.ai.app_registry.exporter import export_agent_bundle
bundle = export_agent_bundle("CRM Lead Assistant")
# Returns dict: {"agents/...": "...", "tools/...": "...", ...}
```

## API Endpoints

All functions are whitelisted and available via Frappe's API:

```javascript
// Discover all apps
frappe.call({
    method: "huf.ai.app_registry.discovery.discover_app_definitions_api",
    callback: (r) => console.log(r.message)
});

// Get status
frappe.call({
    method: "huf.ai.app_registry.discovery.get_app_discovery_status",
    callback: (r) => console.log(r.message)
});

// Export definition
frappe.call({
    method: "huf.ai.app_registry.exporter.export_definition_api",
    args: { doctype: "Agent", name: "CRM Lead Assistant" },
    callback: (r) => console.log(r.message)
});

// Export bundle
frappe.call({
    method: "huf.ai.app_registry.exporter.export_agent_bundle_api",
    args: { agent_name: "CRM Lead Assistant" },
    callback: (r) => console.log(r.message)
});
```

## Validation

The system validates definitions before import:

- **Required fields**: Ensures mandatory fields are present
- **Type checking**: Validates field types
- **Function paths**: Verifies Custom Function/App Provided tools are importable and callable
- **References**: Checks that referenced providers, models, tools, and agents exist
- **Circular dependencies**: Detects circular agent references through tools

## Error Handling

Discovery errors never break `bench migrate` or app installation:

- Invalid JSON files are logged and skipped
- Missing required fields cause that definition to be skipped
- Missing references are logged as warnings but don't block import
- All errors are available in the result dict

## Caching

The system uses file hash-based caching:

- Cache stored in `Agent Settings.last_definition_scans`
- Hash computed from file paths and modification times
- Apps are only re-scanned when files change
- Use `use_cache=True` to enable caching
- Use `rebuild_app_definitions()` to force full re-scan

## Examples

See the `examples/` directory for complete sample definitions:

- `examples/agents/` - Sample agent definitions
- `examples/tools/` - Sample tool definitions
- `examples/prompts/` - Sample prompt templates
- `examples/providers/` - Sample provider declarations
- `examples/models/` - Sample model declarations
- `examples/knowledge/` - Sample knowledge sources
- `examples/triggers/` - Sample trigger configurations

## Testing

Run the test suite:

```bash
# Run all app_registry tests
bench --site <sitename> run-tests --app huf --module huf.ai.app_registry.test_app_registry

# Or run specific test class
bench --site <sitename> run-tests --app huf --test "TestLoader"
```

## Architecture

The system is organized into modules:

- `discovery.py` - Top-level orchestration and public API
- `loader.py` - File scanning and JSON parsing
- `validator.py` - Type-specific validation rules
- `normaliser.py` - Payload transformation for DocType upsert
- `importer.py` - DocType create/update logic
- `exporter.py` - Export DocType back to JSON
- `cache.py` - Cache management and file change detection

## Migration from huf_tools Hook

Apps using the existing `huf_tools` hook can migrate gradually:

1. **Phase 1**: Continue using `huf_tools` - works as before
2. **Phase 2**: Add `huf/tools/*.tool.json` files alongside `huf_tools` - both work
3. **Phase 3**: Remove `huf_tools` entries - file-based definitions take precedence

The hook-based system remains supported indefinitely.

## Security Considerations

- **No secrets in files**: API keys are never stored in definition files
- **Function validation**: All function paths are validated before import
- **Permission checks**: Runtime access governed by standard Frappe permissions
- **Safe evaluation**: Trigger conditions use `safe_eval`, not arbitrary code execution

## Best Practices

1. **Naming**: Use `snake_case` for file names and tool names
2. **Tool naming**: Use `<app>.<action>` convention (e.g., `crm.create_lead`)
3. **Versioning**: Include version field for future migration support
4. **Documentation**: Write clear descriptions - the LLM uses them
5. **Testing**: Validate definitions before committing
6. **Dependencies**: Import order handles dependencies automatically

## Troubleshooting

### Definitions not importing

Check the error log in the result:
```python
result = discover_app_definitions()
print(result["errors"])  # List of errors
print(result["warnings"])  # List of warnings
```

### Cache issues

Force rebuild:
```python
rebuild_app_definitions()
```

### Function path errors

Verify the function is importable:
```python
import frappe
func = frappe.get_attr("my_app.api.my_function")
print(callable(func))  # Should be True
```

## License

Copyright (c) 2025, Tridz Technologies Pvt Ltd - AGPL v3
