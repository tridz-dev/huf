# HUF App Agent Seeding

HUF allows any installed Frappe app to declare AI capabilities (agents, tools, prompts, knowledge sources, and triggers) using plain JSON files. This is similar to Frappe's DocType JSON discovery.

When HUF is installed, it automatically discovers and registers these files. When HUF is not installed, your app continues to function normally with zero runtime cost or dependency errors.

## Folder Convention

Inside your app's Python package root, create a `huf/` directory:

```
myapp/
  myapp/
    huf/
      agents/
        crm_assistant.json
      tools/
        create_lead.json
      prompts/
        lead_summary.json
      knowledge/
        sales_playbook.json
      triggers/
        new_lead_trigger.json
```

HUF will scan these subdirectories for `*.json` files. The directory structure is flat (no nested subdirectories).

## When Does Sync Run?

- Automatically on `bench migrate`
- Automatically on `bench install-app`
- Manually via the "Sync App Seeds" button in the HUF Settings UI

## JSON Format

The JSON schema mirrors the DocType field names (snake_case).

### Agent (`agents/<name>.json`)
```json
{
  "agent_name": "CRM Lead Assistant",
  "description": "Helps sales reps manage leads",
  "provider": "OpenAI",
  "model": "gpt-4o-mini",
  "prompt_mode": "Local",
  "instructions": "You are a CRM assistant...",
  "temperature": 0.3,
  "allow_chat": true,
  "tools": ["create_lead"],
  "knowledge": ["crm_sales_playbook"]
}
```

### Tool (`tools/<name>.json`)
```json
{
  "tool_name": "create_lead",
  "description": "Create a new CRM lead",
  "types": "Custom Function",
  "function_path": "crm.api.leads.create_lead",
  "parameters": [
    {"fieldname": "first_name", "param_type": "Data", "required": 1},
    {"fieldname": "email", "param_type": "Data", "required": 1}
  ]
}
```

### Prompt (`prompts/<name>.json`)
```json
{
  "title": "CRM Lead Summary",
  "category": "CRM",
  "prompt_body": "Summarize this lead: {lead_data}"
}
```

### Knowledge Source (`knowledge/<name>.json`)
```json
{
  "source_name": "crm_sales_playbook",
  "description": "Sales guidelines and objection handling",
  "storage_mode": "SQLite (FTS)",
  "scope": "Global"
}
```

### Trigger (`triggers/<name>.json`)
```json
{
  "trigger_name": "New Lead Followup",
  "agent": "CRM Lead Assistant",
  "trigger_type": "Doc Event",
  "reference_doctype": "Lead",
  "doc_event": "after_insert",
  "disabled": 0
}
```

## Provenance

When HUF imports your files, it adds `source_app` and `source_file` fields to the generated documents. If a document is updated in the UI, it will be overwritten on the next sync.
