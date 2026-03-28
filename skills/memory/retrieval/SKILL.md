# Skill: Memory Retrieval

Retrieve memories and inject them into agent prompts.

## Overview

Retrieval defines **how** memory is accessed during agent execution. Three modes available: inject, tool-only, hybrid.

## Retrieval Modes

### 1. Inject Mode

Memory auto-injected into system prompt at conversation start/before each run.

**Best for**: High-priority profile data, small stable context sets

**Configuration**:
```python
{
    "retrieval_mode": "inject",
    "inject_max_items": 5,
    "inject_max_tokens": 2000,
    "order_by": ["-importance_score", "-created_at"]
}
```

**Example**:
```python
from huf.memory.retrieval import get_retrieval_mode, RetrievalMode

retrieval = get_retrieval_mode("inject")

result = retrieval.retrieve(
    query="user preferences",
    agent_name="my-agent",
    conversation_id="conv_123"
)

# Result:
# {
#     "mode": "inject",
#     "results": [...],
#     "total_found": 10,
#     "injected_count": 5,
#     "estimated_tokens": 800
# }
```

### 2. Tool-Only Mode

No automatic injection. Agent must call `memory_search` tool.

**Best for**: Large memory corpora, rarely-needed data, secondary knowledge

**Configuration**:
```python
{
    "retrieval_mode": "tool_only",
    "tool_enabled": True,
    "tool_default_limit": 10,
    "tool_max_limit": 100
}
```

### 3. Hybrid Mode ⭐ Recommended

Top-K high-priority memory auto-injected. Full memory search tool also available. Injected memory IDs excluded from tool results.

**Best for**: Balanced approach, profile injection + searchable archive

**Configuration**:
```python
{
    "retrieval_mode": "hybrid",
    "inject": {"max_items": 5, "selection": "highest_importance"},
    "tool": {"enabled": True, "default_limit": 10},
    "deduplicate": True
}
```

**Example**:
```python
from huf.memory.retrieval import get_retrieval_mode, RetrievalMode

retrieval = get_retrieval_mode("hybrid")

result = retrieval.retrieve(
    query="travel plans",
    agent_name="my-agent",
    conversation_id="conv_123",
    exclude_injected=True  # Don't show already-injected memories
)

# Result:
# {
#     "mode": "hybrid",
#     "injected": [...],           # Top-K for prompt
#     "injected_count": 5,
#     "tool_available": [...],     # Rest for tool search
#     "tool_count": 15,
#     "total_unique": 20
# }
```

## Prompt Injection

**Location**: `huf/huf/memory/injection.py`

### MemoryContextBuilder

Build memory context blocks for prompt injection:

```python
from huf.memory.injection import MemoryContextBuilder

builder = MemoryContextBuilder(max_tokens=2000)

result = builder.build_memory_context(
    agent_name="my-agent",
    conversation_id="conv_123",
    user_id="user@example.com",
    query="user preferences",  # For relevance ranking
    max_items=5,
    format_style="markdown"  # or "json", "xml"
)

# Result:
# {
#     "context_text": "## Relevant Memory\n\n### Profile: User Preferences\n...",
#     "memories_used": [...],
#     "estimated_tokens": 800,
#     "memory_count": 5
# }
```

### MemoryPromptInjector

Inject memory context into agent prompts:

```python
from huf.memory.injection import MemoryPromptInjector

injector = MemoryPromptInjector()

# Inject before prompt
prompt_with_memory = injector.inject_memory_context(
    prompt="How can I help you today?",
    agent_name="my-agent",
    conversation_id="conv_123",
    retrieval_mode=RetrievalMode.HYBRID,
    max_items=5,
    position="before"  # or "after", "replace"
)

# Result:
# "## Relevant Memory\n\n### Profile: User Preferences\n...
# ---
#
# How can I help you today?"
```

### Convenience Functions

```python
from huf.memory.injection import (
    build_memory_context_for_agent,
    inject_memory_into_prompt
)

# Build context for agent
context = build_memory_context_for_agent(
    agent_name="my-agent",
    user_query="What are my travel plans?",
    conversation_id="conv_123"
)

# Inject into prompt
new_prompt = inject_memory_into_prompt(
    prompt="How can I help?",
    agent_name="my-agent",
    conversation_id="conv_123",
    query="travel plans"  # For relevance search
)
```

## Search

**Location**: `huf/huf/memory/search.py`

### MemorySearcher

```python
from huf.memory.search import MemorySearcher

searcher = MemorySearcher()

results = searcher.search(
    query="dark mode preference",
    filters={
        "agent": "my-agent",
        "scope_type": "user",
        "memory_type": "preference",
        "status": "active"
    },
    limit=10,
    order_by=["-importance_score", "-created_at"]
)
```

### MemoryFilterBuilder

```python
from huf.memory.search import MemoryFilterBuilder

builder = MemoryFilterBuilder()
builder.add_scope_filter(
    agent_name="my-agent",
    conversation_id="conv_123",
    user_id="user@example.com"
)
builder.add_status_filter(status="active")
builder.add_memory_type_filter("preference")

filters = builder.build()
```

### Ranking

Default ranking formula:
```
score = importance_score × 0.4 + 
        recency_weight × 0.3 + 
        scope_relevance × 0.2 + 
        (1 / (1 + retrieval_count)) × 0.1
```

## API Functions

```python
# Get available retrieval modes
huf.memory.retrieval.get_retrieval_modes()
# Returns: [{"id": "inject", "name": "Inject", ...}, ...]

# Test retrieval with mode
huf.memory.retrieval.test_retrieval(
    mode="hybrid",
    agent_name="my-agent",
    query="user preferences"
)

# Preview what would be injected
huf.memory.injection.preview_memory_context(
    agent_name="my-agent",
    conversation_id="conv_123"
)

# Test injection with sample prompt
huf.memory.injection.test_memory_injection(
    prompt="How can I help?",
    agent_name="my-agent"
)
```

## Configuration

### Agent Memory Settings

```python
{
    "enable_memory": True,
    "memory_retrieval_mode": "hybrid",  # inject, tool_only, hybrid
    "memory_max_items": 5,
    "memory_in_prompt_budget": 2000,  # tokens
    "enable_memory_search_tool": True,
    "enable_memory_write_tool": True
}
```

### MemoryRetrievalConfig

```python
from huf.memory.retrieval import MemoryRetrievalConfig, RetrievalMode

config = MemoryRetrievalConfig(
    mode=RetrievalMode.HYBRID,
    inject_max_items=5,
    inject_max_tokens=2000,
    tool_enabled=True,
    tool_default_limit=10,
    tool_max_limit=100,
    order_by=["-importance_score", "-created_at"]
)
```

## Context Format

### Markdown (Default)

```markdown
## Relevant Memory

### Profile: User Preferences
- Language: English
- Timezone: America/New_York
- Theme: Dark

### Session: Travel Planning
- Destination: Tokyo
- Dates: 2024-05-01 to 2024-05-10

_(confidence: 0.95, relevance: 0.88)_
```

### JSON

```json
{
  "relevant_memory": [
    {
      "id": "MEM-xxx",
      "title": "User Preferences",
      "type": "profile",
      "data": {"theme": "dark"},
      "confidence": 0.95
    }
  ]
}
```

### XML

```xml
<memories>
  <memory id="MEM-xxx" type="profile">
    <title>User Preferences</title>
    <data>
      <theme>dark</theme>
    </data>
  </memory>
</memories>
```

## Best Practices

1. **Use hybrid mode for most agents** - Best balance of convenience and control
2. **Set appropriate token budgets** - Don't overwhelm the context window
3. **Use relevance scoring** - Query-based retrieval for better results
4. **Enable deduplication** - Avoid showing same memory twice
5. **Track retrieval metrics** - Monitor which memories are most useful
