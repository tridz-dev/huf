# HUF Memory System - Agent Runner Integration

This document describes how the HUF Memory System integrates with the Agent Runner.

## Overview

The memory system provides:
- **Pre-execution memory injection**: Relevant memories are injected into the agent prompt
- **Post-execution memory capture**: New memories are extracted from agent responses
- **Observability**: Memory metrics are tracked on Agent Run documents

## Integration Points

### 1. Memory Injection (Pre-Run)

**Location**: `huf/ai/agent_integration.py`, in `run_agent_sync()` after knowledge injection

```python
from huf.memory.runner_hooks import pre_run_hook, should_enable_memory

# After building enhanced_prompt...
if should_enable_memory(agent_doc):
    enhanced_prompt = pre_run_hook(agent_doc, enhanced_prompt, conversation)
```

**What it does**:
- Retrieves relevant memories based on agent, conversation, and user context
- Injects formatted memory context into the prompt
- Respects token budgets and importance scoring

### 2. Memory Capture (Post-Run)

**Location**: `huf/ai/agent_integration.py`, in `run_agent_sync()` after success

```python
from huf.memory.runner_hooks import post_run_hook

# After setting run status to Success...
if should_enable_memory(agent_doc):
    post_run_hook(agent_doc, run_doc, conversation, final_output, history)
```

**What it does**:
- Captures the conversation as memories
- Extracts structured data from agent response
- Creates/updates Memory Record documents
- Updates Agent Run observability fields

## Key Components

### MemoryAgentIntegration (`huf/memory/integration.py`)

Main integration class that coordinates:
- Memory retrieval and injection
- Memory capture after runs
- Agent run observability updates

```python
from huf.memory.integration import MemoryAgentIntegration

integration = MemoryAgentIntegration(agent_name)

# Pre-run: Inject memories
enhanced_prompt = integration.inject_memory_context(
    prompt=prompt,
    conversation_id=conversation_id,
    user_id=user_id
)

# Post-run: Capture memories
result = integration.capture_after_run(
    run_id=run_id,
    conversation_id=conversation_id,
    agent_response=agent_response,
    conversation_history=history
)
```

### Runner Hooks (`huf/memory/runner_hooks.py`)

Convenience functions for agent_integration.py:
- `pre_run_hook()` - Simplified injection
- `post_run_hook()` - Simplified capture
- `should_enable_memory()` - Check if memory is enabled
- `get_memory_config()` - Get memory configuration

### Capture Service (`huf/memory/capture/capture_service.py`)

Handles memory capture with support for:
- Multiple capture modes (in_prompt, post_async, rules_only)
- Capture via specialized memory agent
- Background job processing
- Fallback strategies

### Retrieval Service (`huf/memory/retrieval/retrieval_service.py`)

Handles memory retrieval with support for:
- Multiple retrieval modes (inject, tool_only, hybrid)
- Scope-aware filtering (conversation, user, agent, global)
- Token budgeting
- Relevance ranking

## Configuration

### Agent-Level Configuration

Enable memory for an agent by setting either:
- `enable_memory` checkbox = True
- `memory_policy` link to a Memory Policy document

### Memory Policy DocType

Create a Memory Policy to configure:
- **Capture Mode**: How memories are captured (in_prompt, post_async, rules_only)
- **Retrieval Mode**: How memories are retrieved (inject, tool_only, hybrid)
- **Max Items**: Maximum memories to inject
- **Max Tokens**: Token budget for injected memories
- **Scope Type**: Default scope for captured memories

### Agent Run Observability

The following fields on Agent Run track memory operations:
- `memory_capture_triggered` - Whether capture was attempted
- `memory_capture_mode` - Mode used (main_agent, memory_agent, post_run_llm, etc.)
- `memory_records_created` - Number of records created
- `memory_records_updated` - Number of records updated
- `memory_records_skipped` - Number of captures skipped
- `memory_capture_latency_ms` - Time spent on capture
- `memory_capture_cost` - Estimated cost of capture
- `memory_index_jobs_started` - Number of index jobs queued
- `memory_error_log` - Error details if capture failed

## Capture Modes

### 1. In-Prompt Capture (C1)

Memory extraction happens during the main agent execution. The agent returns both response and memory updates.

**Pros**: Immediate capture, agent-aware extraction  
**Cons**: Adds latency to response

**Use when**: High-quality extraction is more important than latency

### 2. Post-Run Async Capture (C2)

Memory extraction happens in background after user response is returned.

**Pros**: Zero latency impact on user response  
**Cons**: Eventual consistency, may fail silently

**Use when**: Response time is critical

### 3. Rules-Only Capture

Memory extraction uses only rules (no LLM calls).

**Pros**: Fast, deterministic, low cost  
**Cons**: Less flexible than LLM extraction

**Use when**: Simple, well-defined memory patterns

## Retrieval Modes

### 1. Inject Mode

Memories are automatically injected into the agent prompt.

**Best for**: High-priority, always-relevant memories

### 2. Tool-Only Mode

Memories are only available via explicit tool calls.

**Best for**: Large memory sets, memory search by query

### 3. Hybrid Mode

High-priority memories are injected; additional memories available via tool.

**Best for**: General use - combines benefits of both

## Testing

Run the integration tests:

```bash
cd ~/frappe-bench
bench --site [site] run-tests --app huf --test-file test_memory_integration.py
```

Tests cover:
- End-to-end memory flow (capture → storage → retrieval → injection)
- Different capture modes
- Different retrieval modes
- Agent run observability
- Scope filtering
- Importance ranking

## Error Handling

The integration is designed to be resilient:

1. **Fail-safe**: If memory operations fail, the agent still runs
2. **Logged**: All errors are logged to Agent Run or Error Log
3. **Observable**: Failed captures are visible in run metrics
4. **Retry**: Background jobs have built-in retry logic

## Migration Guide

### For Existing Agents

1. Enable memory on the Agent document:
   - Check "Enable Memory" OR
   - Link to a Memory Policy

2. No code changes needed - memory hooks are automatic

### For New Agents

1. Create Agent as usual
2. Configure Memory Policy (optional but recommended)
3. Enable memory via checkbox or policy

## Troubleshooting

### Memory not being injected
- Check `enable_memory` or `memory_policy` on Agent
- Verify memories exist with matching scope
- Check logs for injection errors

### Memory not being captured
- Check Agent Run `memory_capture_triggered` field
- Review `memory_error_log` for errors
- Verify capture service configuration

### Performance issues
- Reduce `inject_max_items` in Memory Policy
- Reduce `inject_max_tokens` in Memory Policy
- Switch to `post_async` capture mode
- Use `rules_only` capture for simpler patterns
