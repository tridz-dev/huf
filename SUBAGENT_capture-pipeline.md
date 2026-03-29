# Subagent Task: capture-pipeline

## Mission
Implement the memory capture pipeline with all capture modes and triggers.

## Input Files (READ THESE FIRST)
- `~/code/huf-memory/tech_specs/CAPTURE_RETRIEVAL.md` - Capture modes specification
- `~/code/huf-memory/doctype_designs/memory_record.json` - Memory Record structure
- `~/code/huf-memory/doctype_designs/memory_policy.json` - Policy configuration
- `~/code/huf-memory/PRD.md` - Sections 11-12 (Capture Modes & Triggers)

## Deliverables

### 1. Capture Pipeline Module
Create: `huf/huf/memory/capture_pipeline.py`

Main class `MemoryCapturePipeline` with methods:

#### Capture Entry Points
- `capture_in_prompt(agent_run, conversation, current_turn_data)` - In-prompt capture
- `capture_post_response_sync(agent_run, conversation)` - Synchronous post-response
- `capture_post_response_async(agent_run, conversation)` - Queue background job
- `capture_conversation_end(conversation)` - Conversation end handler
- `capture_manual(conversation, data)` - Manual capture API

#### Trigger Evaluation
- `should_capture(policy, run_count, turn_count, trigger_type)` - Check if capture should run
- `is_conversation_ended(conversation)` - Check conversation end state
- `check_idle_timeout(conversation)` - Check if idle timeout reached

### 2. Background Job Handler
Create: `huf/huf/memory/capture_worker.py`

Functions:
- `process_async_capture(agent_run_name)` - RQ job entry point
- `extract_memory_from_conversation(conversation, policy)` - LLM extraction logic
- `create_memory_record(data, policy, context)` - Record creation

### 3. Capture Strategies
Create: `huf/huf/memory/capture_strategies.py`

Classes:
- `BaseCaptureStrategy` - Abstract base
- `MainAgentCapture` - In-prompt capture via main agent
- `MemoryAgentCapture` - Delegated to specialized memory agent
- `PostRunLLMCapture` - Post-run LLM extraction
- `RulesOnlyCapture` - Deterministic rule-based capture

### 4. Conversation End Detection
Create: `huf/huf/memory/conversation_end_detector.py`

Functions:
- `detect_manual_close(conversation)` - User/admin closed
- `detect_idle_timeout(conversation, timeout_minutes)` - Inactivity based
- `detect_heuristic_close(conversation)` - Agent classification based
- `detect_workflow_completion(conversation)` - Workflow state based

### 5. Memory Extraction Service
Create: `huf/huf/memory/extraction_service.py`

Class `MemoryExtractionService`:
- `extract_with_prompt(conversation, capture_prompt)` - LLM call for extraction
- `extract_with_schema(conversation, schema_json)` - Schema-constrained extraction
- `generate_summary(raw_data)` - Generate text summary
- `validate_extraction(data, schema)` - JSON Schema validation

### 6. Hooks Integration
Modify/create: `huf/huf/hooks.py` additions

Add hooks:
- `on_agent_run_complete` - Trigger post-run capture
- `on_conversation_close` - Trigger conversation-end capture
- `scheduler_events` - For scheduled capture

## Capture Modes to Implement

### Mode 1: In-prompt Capture
- Injected into main agent prompt
- Agent decides what to capture inline
- Returns structured JSON as part of response
- Parsed and stored immediately

### Mode 2: Post-response Sync Capture
- Runs after user-facing response
- Same request, adds latency
- Calls extraction service synchronously
- Stores before returning to user

### Mode 3: Post-response Async Capture
- Queues background job via RQ
- Returns to user immediately
- Worker processes extraction later
- Updates conversation with results

### Mode 4: Specialized Memory Agent
- Configurable separate agent
- May use cheaper/faster model
- Dedicated extraction prompt
- Called as subprocess/tool

### Mode 5: Rules-only Capture
- No LLM involved
- Deterministic field extraction
- For exact values (timestamps, IDs)
- Fast, no cost

## Trigger Types
- `every_run` - Capture on every agent run
- `every_n_runs` - Capture every N runs
- `every_n_turns` - Capture every N conversation turns
- `after_tool_call` - Capture after specific tool usage
- `final_response_only` - Only on final response
- `conversation_end` - When conversation closes
- `idle_timeout` - After inactivity period
- `manual` - Explicit user/admin trigger
- `scheduled` - Cron-based scheduled capture

## Commits Required
1. `feat(memory): implement in-prompt capture mode`
2. `feat(memory): implement post-response sync capture`
3. `feat(memory): implement post-response async capture with RQ`
4. `feat(memory): implement specialized memory agent capture`
5. `feat(memory): implement rule-only capture mode`
6. `feat(memory): implement conversation-end detection`

## Success Criteria
- All 5 capture modes function correctly
- Triggers fire at appropriate times
- Async capture queues jobs properly
- Extraction produces valid Memory Records
- Conversation-end detection works for all strategies