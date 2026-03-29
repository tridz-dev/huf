# Subagent Task: backend-doctypes

## Mission
Implement all Frappe DocType infrastructure for the HUF Memory System. Convert JSON designs to actual Frappe DocType files with proper controllers.

## Input Files (READ THESE FIRST)
- `~/code/huf-memory/doctype_designs/memory_record.json` - Memory Record DocType schema
- `~/code/huf-memory/doctype_designs/memory_policy.json` - Memory Policy DocType schema
- `~/code/huf-memory/doctype_designs/memory_profile.json` - Memory Profile DocType schema
- `~/code/huf-memory/huf/huf/doctype/memory_record_tag/` - Existing child table (needs controller completion)

## Deliverables

### 1. Memory Record DocType
Create: `huf/huf/doctype/memory_record/`
- `memory_record.json` - Full DocType definition matching the JSON design
- `memory_record.py` - Controller with methods:
  - `validate()` - Validate JSON data fields
  - `before_insert()` - Set defaults, generate title if empty
  - `after_insert()` - Trigger indexing if configured
  - `on_update()` - Handle status changes
  - `update_retrieval_stats()` - Increment retrieval count
  - `supersede()` - Mark as superseded and link to replacement
  - `search_by_scope(scope_type, scope_key)` - Class method for scope queries

### 2. Memory Policy DocType
Create: `huf/huf/doctype/memory_policy/`
- `memory_policy.json` - Full DocType definition
- `memory_policy.py` - Controller with methods:
  - `validate()` - Validate frequency values
  - `get_effective_config(agent)` - Return merged config for agent
  - `should_capture(run_count, turn_count)` - Check if capture should trigger

### 3. Memory Profile DocType
Create: `huf/huf/doctype/memory_profile/`
- `memory_profile.json` - Full DocType definition
- `memory_profile.py` - Controller with methods:
  - `validate()` - Validate JSON schema
  - `get_default_profile(category)` - Class method to get system profile
  - `apply_to_agent(agent)` - Apply profile defaults to agent

### 4. Memory Record Tag Controller
Complete: `huf/huf/doctype/memory_record_tag/memory_record_tag.py`
- Add proper controller methods for the child table

### 5. Agent DocType Extension
Modify existing: `huf/huf/doctype/agent/agent.json`
Add fields (new section "Memory & Learning"):
- `enable_memory` (Check)
- `memory_policy` (Link → Memory Policy)
- `default_memory_scope_type` (Select)
- `memory_retrieval_mode` (Select: inject/tool_only/hybrid)
- `memory_in_prompt_budget` (Int)
- `enable_memory_search_tool` (Check)
- `enable_memory_write_tool` (Check)
- `memory_profile` (Link → Memory Profile)
- `memory_agent` (Link → Agent)
- `memory_run_order` (Select)
- `memory_max_items` (Int)
- `memory_index_backend_default` (Select)
- `memory_visibility_default` (Select)

### 6. Agent Conversation Extension
Modify existing: `huf/huf/doctype/agent_conversation/agent_conversation.json`
Add fields:
- `memory_scope_override` (Data)
- `memory_scope_key_override` (Data)
- `memory_capture_enabled_override` (Check)
- `memory_turn_count` (Int)
- `memory_last_capture_at` (Datetime)
- `conversation_end_state` (Select)
- `ended_at` (Datetime)
- `idle_expires_at` (Datetime)

### 7. Agent Run Extension
Modify existing: `huf/huf/doctype/agent_run/agent_run.json`
Add fields:
- `memory_capture_triggered` (Check)
- `memory_capture_mode` (Data)
- `memory_records_created` (Int)
- `memory_records_updated` (Int)
- `memory_records_skipped` (Int)
- `memory_index_jobs_started` (Int)
- `memory_capture_latency_ms` (Int)
- `memory_capture_cost` (Currency)
- `memory_error_log` (Text)

## Technical Requirements
- Use proper Frappe DocType JSON format (not the design JSON format)
- Include all permissions as specified in design files
- Add search_fields, title_field, sort_field configurations
- Controllers must extend `from frappe.model.document import Document`
- Include docstrings and type hints
- Add `__init__.py` files where needed

## Commits Required
1. `feat(memory): implement Memory Record DocType with controller`
2. `feat(memory): implement Memory Policy DocType with controller`
3. `feat(memory): implement Memory Profile DocType with controller`
4. `feat(memory): complete Memory Record Tag child table`
5. `feat(memory): add memory fields to Agent, Agent Conversation, Agent Run`

## Success Criteria
- All DocTypes load without errors in Frappe bench
- Can create, read, update, delete Memory Records via UI
- Controllers have all specified methods implemented
- Fields appear correctly in Agent form with Memory tab