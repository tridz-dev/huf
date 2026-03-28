# Skill: Memory Capture

Capture memories from agent conversations using various modes and triggers.

## Overview

Memory capture defines **who** performs extraction and **when** it happens during the request lifecycle.

## Capture Modes

### 1. In-Prompt Capture (`in_prompt`)

**When**: During main agent inference  
**Latency**: Zero (part of main request)  
**Producer**: Main agent

**Use Case**: Low-latency session state, simple preference updates

**Configuration**:
```python
{
    "capture_mode": "in_prompt",
    "capture_prompt": "Update memory with user preferences...",
    "schema_json": {...},
    "require_json_schema_match": True
}
```

**Example**:
```python
from huf.memory.capture import InPromptCapture

capture = InPromptCapture({
    "capture_prompt": "Extract user preferences from conversation",
    "require_json_schema_match": True,
    "schema_json": {
        "type": "object",
        "properties": {
            "theme": {"type": "string"},
            "language": {"type": "string"}
        }
    }
})

result = capture.execute({
    "response_data": {
        "memory_update": {
            "theme": "dark",
            "language": "english"
        }
    }
})
```

### 2. Post-Response Synchronous (`post_sync`)

**When**: After main response, before returning to user  
**Latency**: High (blocks user response)  
**Producer**: Main agent or memory agent

**Use Case**: Critical profile updates, highly structured extractions

**Configuration**:
```python
{
    "capture_mode": "post_sync",
    "capture_agent": None,  # or specific agent name
    "timeout_seconds": 10,
    "fallback_on_error": "skip"  # or "fail"
}
```

### 3. Post-Response Asynchronous (`post_async`) ⭐ Recommended

**When**: Background job after user response sent  
**Latency**: Zero (non-blocking)  
**Producer**: Main agent, memory agent, or post-run processor

**Use Case**: Travel capture, CRM enrichment, learned summaries, long conversations

**Configuration**:
```python
{
    "capture_mode": "post_async",
    "capture_agent": "memory-extractor-v1",
    "queue_name": "memory_capture",
    "retry_count": 3,
    "max_context_turns": 20
}
```

**Example**:
```python
from huf.memory.capture import PostAsyncCapture

capture = PostAsyncCapture({
    "queue_name": "memory_capture",
    "retry_count": 3,
    "max_context_turns": 20
})

result = capture.execute({
    "conversation_id": "conv_123",
    "run_id": "run_456",
    "conversation": {...},
    "agent_response": "..."
})
# Returns: {"job_enqueued": True, "job_name": "...", "async": True}
```

### 4. Specialized Memory Agent (`specialized_agent`)

**When**: Configurable (sync or async)  
**Latency**: Varies  
**Producer**: Dedicated memory agent instance

**Use Case**: Strict schemas, domain-specific extraction, cost optimization

**Configuration**:
```python
{
    "capture_mode": "specialized_agent",
    "memory_agent": "extractor-agent-uuid",
    "execution_timing": "post_response_async",  # or "sync"
    "pass_full_history": True,
    "pass_summary_only": False
}
```

**Example**:
```python
from huf.memory.capture import SpecializedAgentCapture

capture = SpecializedAgentCapture({
    "memory_agent": "travel-memory-extractor",
    "execution_timing": "post_response_async"
})

result = capture.execute({
    "conversation_id": "conv_123",
    "conversation": {...}
})
```

### 5. Rule-Only Capture (`rules_only`)

**When**: Deterministic (sync)  
**Latency**: Minimal (no LLM call)  
**Producer**: Rule engine

**Use Case**: Exact identifiers, timestamps, state transitions, system events

**Rule Types**:
- `static` - Fixed value
- `context` - Extract from context
- `regex` - Pattern match
- `tool` - Capture tool outputs
- `computed` - Derived fields

**Configuration**:
```python
{
    "capture_mode": "rules_only",
    "rules": [
        {"field": "user_id", "source": "context", "path": "user.id"},
        {"field": "captured_at", "source": "static", "value": "{{ now() }}"},
        {"field": "intent", "source": "regex", "pattern": "book.*flight", "on_match": "flight_booking"},
        {"field": "turn_count", "source": "computed", "formula": "turn_count"}
    ]
}
```

**Example**:
```python
from huf.memory.capture import RuleOnlyCapture

capture = RuleOnlyCapture({
    "rules": [
        {"field": "user_id", "source": "context", "path": "user_id"},
        {"field": "timestamp", "source": "static", "value": "{{ now() }}"},
        {"field": "booking_type", "source": "regex", "pattern": "(flight|hotel|car)", "source_text": "user_messages"}
    ]
})

result = capture.execute({
    "user_id": "user@example.com",
    "conversation": {
        "messages": [
            {"role": "user", "content": "I want to book a flight to Paris"}
        ]
    }
})
# Returns: {"payload": {"user_id": "...", "timestamp": "...", "booking_type": "flight"}}
```

## Capture Processor

**Location**: `huf/huf/memory/processor.py`

The `CaptureProcessor` orchestrates the entire capture flow:

```python
from huf.memory.processor import CaptureProcessor

processor = CaptureProcessor({
    "capture": {"capture_mode": "post_async"},
    "triggers": [{"trigger_type": "every_run"}]
})

result = processor.process({
    "conversation_id": "conv_123",
    "run_id": "run_456",
    "agent_id": "my-agent",
    "conversation": {...},
    "agent_response": "..."
})

# Result includes:
# - capture_triggered: bool
# - records_created: int
# - records_updated: int
# - latency_ms: int
```

## Factory Function

```python
from huf.memory.capture import get_capture_mode

# Get capture mode by configuration
capture = get_capture_mode({
    "capture_mode": "post_async",  # or in_prompt, post_sync, specialized_agent, rules_only
    "queue_name": "memory_capture"
})

result = capture.execute(context)
```

## Async Processing

Background job handler for async capture:

```python
from huf.memory.capture import process_async_capture

# This is called by Frappe's background job system
process_async_capture(
    conversation_id="conv_123",
    run_id="run_456",
    snapshot={...},  # Context snapshot
    config={"capture_mode": "post_sync", ...}
)
```

## Best Practices

1. **Use `post_async` for most cases** - Non-blocking, good for user experience
2. **Use `post_sync` for critical updates** - Ensures consistency before response
3. **Use `specialized_agent` for complex extraction** - Better quality, cost optimization
4. **Use `rules_only` for deterministic data** - Fast, no LLM cost
5. **Always validate schema** when using structured capture
