# Skill: Memory Tools

Use memory tools in agents for searching, retrieving, and writing memories.

## Overview

Memory tools allow agents to interact with the memory system during execution. They can search for relevant memories, retrieve recent memories, and write new memories.

## Available Tools

| Tool | Purpose | Whitelisted |
|------|---------|-------------|
| `memory_search` | Search memories with filters | Yes |
| `memory_get_recent` | Get recent memories | Yes |
| `memory_get_by_type` | Get memories by type | Yes |
| `memory_get_by_scope` | Get memories by scope | Yes |
| `memory_write` | Write/update memory | Yes |

## Tool Registration

Memory tools are automatically registered when `enable_memory_search_tool` or `enable_memory_write_tool` is enabled on the Agent.

**Agent Configuration**:
```python
{
    "enable_memory": True,
    "enable_memory_search_tool": True,
    "enable_memory_write_tool": True,
    "memory_retrieval_mode": "hybrid"  # inject, tool_only, hybrid
}
```

**Manual Registration**:
```python
from huf.memory.retrieval.memory_search_tool import memory_search
from huf.memory.retrieval.memory_write_tool import memory_write

# Register with agent
agent_tools = [
    {
        "tool_name": "memory_search",
        "function": memory_search,
        "description": "Search for memory records..."
    },
    {
        "tool_name": "memory_write",
        "function": memory_write,
        "description": "Write a new memory record..."
    }
]
```

## memory_search

Search for memory records with various filters.

**Location**: `huf/huf/memory/retrieval/memory_search_tool.py`

### Signature

```python
def memory_search(
    query: str = None,
    memory_type: str = None,
    memory_types: List[str] = None,
    scope_type: str = None,
    tags: List[str] = None,
    min_confidence: float = None,
    min_importance: float = None,
    limit: int = 10,
    offset: int = 0,
    agent: str = None,
    conversation: str = None,
    include_injected: bool = True,
) -> Dict[str, Any]
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | str | None | Search text to match against content |
| `memory_type` | str | None | Filter by single type |
| `memory_types` | List[str] | None | Filter by multiple types |
| `scope_type` | str | None | conversation, user, agent, namespace, global |
| `tags` | List[str] | None | Filter by tags (must have all) |
| `min_confidence` | float | None | Minimum confidence (0.0-1.0) |
| `min_importance` | float | None | Minimum importance (0.0-1.0) |
| `limit` | int | 10 | Max results (max: 100) |
| `offset` | int | 0 | Pagination offset |
| `agent` | str | None | Agent ID (auto-resolved) |
| `conversation` | str | None | Conversation ID (auto-resolved) |
| `include_injected` | bool | True | Include already-injected memories |

### Memory Types

Valid `memory_type` values:
- `profile` - User profile information
- `session_state` - Current session context
- `preference` - User preferences
- `fact` - Factual information
- `plan` - Plans or goals
- `observation` - Observed behavior
- `insight` - Derived insights
- `domain_object` - Domain-specific objects
- `custom` - Custom/uncategorized

### Scope Types

Valid `scope_type` values:
- `conversation` - Current conversation only
- `user` - Across all user's conversations
- `agent` - Shared across agent's users
- `namespace` - Custom namespace
- `global` - All agents

### Examples

**Basic Search**:
```python
result = memory_search(query="dark mode preference")
# Returns: {"success": True, "memories": [...], "total_found": 5}
```

**Filter by Type**:
```python
result = memory_search(
    query="travel",
    memory_type="plan"
)
```

**Multiple Types**:
```python
result = memory_search(
    memory_types=["preference", "fact"],
    min_confidence=0.8
)
```

**By Scope**:
```python
result = memory_search(
    scope_type="user",
    tags=["ui", "important"]
)
```

**Pagination**:
```python
result = memory_search(
    query="project",
    limit=20,
    offset=20  # Get page 2
)
```

### Response Format

```python
{
    "success": True,
    "memories": [
        {
            "name": "MEM-2024-00001",
            "title": "User Preference: Dark Mode",
            "memory_type": "preference",
            "summary": "User prefers dark mode interface",
            "data": {"theme": "dark", "contrast": "high"},
            "score": 0.95,
            "confidence": 1.0,
            "importance": 0.8,
            "scope_type": "user",
            "scope_key": "user@example.com",
            "created_at": "2024-01-15T10:30:00",
            "tags": ["ui", "preference"]
        }
    ],
    "total_found": 3,
    "returned_count": 1,
    "query": "dark mode preference",
    "filters": {...},
    "pagination": {
        "limit": 10,
        "offset": 0,
        "has_more": False
    }
}
```

## memory_get_recent

Get recently created memories ordered by creation time.

### Signature

```python
def memory_get_recent(
    agent: str = None,
    conversation: str = None,
    memory_type: str = None,
    limit: int = 5,
) -> Dict[str, Any]
```

### Examples

```python
# Get 5 most recent memories
result = memory_get_recent(limit=5)

# Recent preferences
result = memory_get_recent(
    memory_type="preference",
    limit=10
)

# Recent in conversation
result = memory_get_recent(
    conversation="conv_123",
    limit=3
)
```

## memory_get_by_type

Get memories filtered by specific type.

### Signature

```python
def memory_get_by_type(
    memory_type: str,
    agent: str = None,
    conversation: str = None,
    limit: int = 10,
) -> Dict[str, Any]
```

### Examples

```python
# Get all facts
result = memory_get_by_type("fact", limit=20)

# Get plans for conversation
result = memory_get_by_type(
    memory_type="plan",
    conversation="conv_123"
)
```

## memory_get_by_scope

Get memories within a specific scope.

### Signature

```python
def memory_get_by_scope(
    scope_type: str,
    scope_key: str = None,
    agent: str = None,
    limit: int = 10,
) -> Dict[str, Any]
```

### Examples

```python
# Get user-scoped memories
result = memory_get_by_scope("user", limit=10)

# Get agent-scoped memories
result = memory_get_by_scope("agent", agent="my-agent")

# Get namespace memories
result = memory_get_by_scope(
    scope_type="namespace",
    scope_key="project-alpha"
)
```

## memory_write

Write a new memory record or update existing.

**Location**: `huf/huf/memory/retrieval/memory_write_tool.py`

### Signature

```python
def memory_write(
    title: str,
    data: Dict[str, Any],
    memory_type: str = "custom",
    summary: str = None,
    scope_type: str = None,
    scope_key: str = None,
    tags: List[str] = None,
    confidence: float = None,
    importance: float = None,
    update_existing: bool = True,
    agent: str = None,
    conversation: str = None,
) -> Dict[str, Any]
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `title` | str | required | Memory title |
| `data` | Dict | required | Structured data |
| `memory_type` | str | "custom" | Type classification |
| `summary` | str | None | Text summary |
| `scope_type` | str | None | Auto-resolved |
| `scope_key` | str | None | Auto-resolved |
| `tags` | List[str] | None | Tags |
| `confidence` | float | None | Confidence score |
| `importance` | float | None | Importance score |
| `update_existing` | bool | True | Update if similar exists |
| `agent` | str | None | Auto-resolved |
| `conversation` | str | None | Auto-resolved |

### Examples

**Create New Memory**:
```python
result = memory_write(
    title="User Preference: Dark Mode",
    data={"theme": "dark", "contrast": "high"},
    memory_type="preference",
    summary="User prefers dark mode interface",
    tags=["ui", "preference"],
    confidence=1.0,
    importance=0.8
)
# Returns: {"success": True, "record_id": "MEM-xxx", "created": True}
```

**Update Existing**:
```python
# If similar memory exists (same type, scope), it will be updated
result = memory_write(
    title="User Preference",
    data={"theme": "dark", "accent": "blue"},
    memory_type="preference",
    update_existing=True
)
# Returns: {"success": True, "record_id": "MEM-xxx", "updated": True}
```

**With Explicit Scope**:
```python
result = memory_write(
    title="Project Decision",
    data={"decision": "Use PostgreSQL", "rationale": "..."},
    memory_type="insight",
    scope_type="namespace",
    scope_key="project-alpha",
    tags=["decision", "database"]
)
```

### Response Format

```python
# Created new
{
    "success": True,
    "record_id": "MEM-2024-00001",
    "created": True,
    "updated": False,
    "title": "User Preference: Dark Mode"
}

# Updated existing
{
    "success": True,
    "record_id": "MEM-2024-00001",
    "created": False,
    "updated": True,
    "title": "User Preference: Dark Mode"
}
```

## Tool Usage Patterns

### Pattern 1: Context-Aware Response

```python
# Agent uses memory to personalize response
memories = memory_search(query="user preferences")

# Agent responds using memory context
"I see you prefer dark mode. Here's the information..."
```

### Pattern 2: Fact Verification

```python
# Agent checks memory before answering
facts = memory_get_by_type("fact", limit=5)

# Verify against memory
"Based on what you told me before..."
```

### Pattern 3: Progressive Learning

```python
# Agent learns from conversation
memory_write(
    title="Learned: User's Company",
    data={"company": "Acme Corp", "role": "Developer"},
    memory_type="fact",
    confidence=0.9
)
```

### Pattern 4: Session Continuity

```python
# Check previous session state
state = memory_get_recent(memory_type="session_state", limit=1)

"Continuing from where we left off..."
```

## Error Handling

All tools return standardized error responses:

```python
{
    "success": False,
    "error": "Description of what went wrong",
    "details": {...}  # Additional context if available
}
```

Common errors:
- Agent not found
- Invalid memory_type
- Invalid scope_type
- Database errors
- Permission denied

## Best Practices

1. **Always check `success`** before using results
2. **Handle empty results gracefully**
3. **Use appropriate memory types** - Improves retrieval
4. **Set confidence scores** - Mark uncertain memories lower
5. **Tag memories** - Makes filtering easier
6. **Update rather than duplicate** - Use `update_existing=True`
7. **Respect scope boundaries** - Don't write to wrong scope
8. **Keep data structured** - Easier to use later

## Integration with Agent Prompt

Tell agents about memory tools in their instructions:

```markdown
You have access to memory tools:

- memory_search: Find relevant memories by query
- memory_get_recent: Get recent memories
- memory_get_by_type: Get memories of specific type
- memory_write: Save new information to memory

Use these to:
1. Check for user preferences before making suggestions
2. Remember facts the user shares
3. Build up knowledge over time

When you learn something important, use memory_write to save it.
```
