# withkids tracker — Hub round 4 (create_agent_tool rework + table-tool pattern)

Repo: /Users/safwan/Code/Docker/frappe_docker/development/16/apps/huf · Site: huf.localhost:8000

## Root causes (parent-diagnosed)

- create_agent_tool hardcodes types="Custom Function" with no function_path → Agent Tool Function.validate_json (agent_tool_function.py:678-681) hard-requires function_path → tool could NEVER succeed ("Function path is required for Custom Functions").
- Document types (Create Document, Get List, Update Document, Delete Document, Get/Set Value, multi-doc variants) are REAL declarative tools: they execute via handle_* in sdk_tools.py bound to reference_doctype, no function_path needed.
- Orchestrator instructions didn't tell the agent how to give a table agent data tools → it invented per-table Custom Function tools.

## Tasks

| id | task | kid | status | files |
|----|------|-----|--------|-------|
| R4-T1 | Rework create_agent_tool: types whitelist (document types), reference_doctype, reject Custom Function; registry schema/desc; tests | coder | in_progress | huf/ai/tools/builder.py, huf/ai/tools/_registry.py, huf/ai/tests/test_builder_tools.py |
| R4-T2 | Instructions: table-agent tool pattern (generic row tools OR named document tools) | parent | pending | huf/huf/agents/hub-orchestrator.json + live doc |
| R4-T3 | Migrate + replay failing scenario + verify | parent | pending | — |
