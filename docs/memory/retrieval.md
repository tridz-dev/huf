# Memory Retrieval

Retrieval is how stored memories are found and made available to agents. Understanding retrieval mechanisms is key to building effective memory-enabled agents.

## Retrieval Modes

### 1. Inject Mode

**How it works**: Relevant memories are automatically included in the agent's prompt context.

```
┌─────────────────────────────────────────────────────────┐
│ System Prompt                                           │
├─────────────────────────────────────────────────────────┤
│ You are a helpful assistant...                          │
│                                                         │
│ Relevant memories:                                      │
│ • User prefers dark mode                                │
│ • User works in marketing                               │
│ • User is learning Python                               │
├─────────────────────────────────────────────────────────┤
│ User: What should I learn next?                         │
└─────────────────────────────────────────────────────────┘
```

**Configuration**:
```python
retrieval_mode = "inject"
max_items_to_inject = 5
max_tokens_to_inject = 1000
```

**Pros**:
- Agent always has relevant context
- No agent code changes needed
- Natural integration

**Cons**:
- Uses prompt tokens
- May include irrelevant memories
- Fixed context window usage

**Best For**:
- Personal assistants
- Long-running relationships
- Context-heavy tasks

---

### 2. Tool-Only Mode

**How it works**: Agent must explicitly request memories via a tool.

```
User: Do you remember my preferences?
     ↓
Agent: [Thinks] I should search my memory
     ↓
Agent: [Calls memory_search tool with query="user preferences"]
     ↓
System: [Returns matching memories]
     ↓
Agent: Yes, you prefer dark mode and work in marketing...
```

**Configuration**:
```python
retrieval_mode = "tool_only"
enable_memory_search_tool = True
```

**Pros**:
- Agent controls when to search
- No automatic token usage
- More selective

**Cons**:
- Agent must be trained to use tool
- May miss important context
- Extra tool calls

**Best For**:
- Resource-constrained environments
- Agents that need specific control
- Question-answering scenarios

---

### 3. Hybrid Mode ⭐ Recommended

**How it works**: Combines automatic injection with on-demand tool access.

```
┌─────────────────────────────────────────────────────────┐
│ Automatic Injection (Top N by relevance)                │
│ • User prefers dark mode                                │
│ • User works in marketing                               │
├─────────────────────────────────────────────────────────┤
│ [Agent can also call memory_search for more]            │
└─────────────────────────────────────────────────────────┘
```

**Configuration**:
```python
retrieval_mode = "hybrid"
max_items_to_inject = 3  # Small automatic set
enable_memory_search_tool = True  # Allow more on demand
```

**Pros**:
- Best of both worlds
- Critical context always available
- Agent can dig deeper when needed

**Cons**:
- More complex
- Requires both infrastructure pieces

**Best For**:
- Most production use cases
- Complex agents
- Dynamic contexts

## Search Mechanisms

### Full-Text Search (FTS)

**How it works**: Keyword-based search using database full-text indexes.

```python
# Search query
search_memories(query="dark mode preferences")

# Returns memories where:
# - "dark" appears in title/summary
# - "mode" appears in title/summary
# - "preferences" appears in title/summary
```

**Ranking**: Based on term frequency and field weights.

**Best For**:
- Exact keyword matching
- Named entities (people, places, products)
- Quick filtering

### Vector Search (Semantic)

**How it works**: Embeddings capture semantic meaning for similarity search.

```python
# Search query
search_memories(query="what display settings does the user like?")

# Returns memories about:
# - dark mode preference
# - theme settings
# - UI customization
# (even if they don't use those exact words)
```

**Ranking**: Based on cosine similarity of embeddings.

**Best For**:
- Conceptual queries
- Natural language questions
- Finding related but not identical content

### Hybrid Search

**How it works**: Combines FTS and vector results with ranking.

```python
# Query processed both ways
fts_results = full_text_search(query)
vector_results = semantic_search(query)

# Combined ranking
final_results = reciprocal_rank_fusion(fts_results, vector_results)
```

**Best For**:
- Maximum recall
- Balancing precision and semantic understanding
- Production systems

## Retrieval Pipeline

### Step 1: Query Generation

The system generates multiple query representations:

```python
# Original user message
"What was I working on yesterday?"

# Generated queries:
queries = [
    "working yesterday projects tasks",
    "previous day work activities",
    "recent work history"
]
```

### Step 2: Candidate Retrieval

Fetch candidates from all indexes:

```python
# FTS candidates
fts_candidates = search_fts(queries, limit=50)

# Vector candidates  
vector_candidates = search_vector(queries, limit=50)

# Merge and deduplicate
candidates = merge_results(fts_candidates, vector_candidates)
```

### Step 3: Filtering

Apply policy and scope filters:

```python
# Scope filter
if scope_type == "user":
    candidates = filter_by_user(candidates, current_user)

# Status filter
candidates = filter_by_status(candidates, "active")

# Temporal filter
if query_contains_time_reference:
    candidates = filter_by_date(candidates, time_range)
```

### Step 4: Ranking

Score and rank candidates:

```python
for memory in candidates:
    score = (
        relevance_score * 0.4 +
        recency_score * 0.2 +
        importance_score * 0.2 +
        retrieval_frequency_score * 0.1 +
        confidence_score * 0.1
    )
    memory.rerank_score = score

# Sort by score
ranked = sorted(candidates, key=lambda m: m.rerank_score, reverse=True)
```

### Step 5: Selection

Select top memories respecting budget:

```python
selected = []
tokens_used = 0

for memory in ranked:
    memory_tokens = estimate_tokens(memory.summary)
    
    if len(selected) >= max_items:
        break
        
    if tokens_used + memory_tokens > max_tokens:
        # Try to find a shorter memory
        continue
        
    selected.append(memory)
    tokens_used += memory_tokens
```

### Step 6: Formatting

Format for injection:

```python
# Default format
memory_block = """
Relevant memories:
{memories}
"""

# Or structured
memory_block = json.dumps([{
    "type": m.memory_type,
    "content": m.summary,
    "confidence": m.confidence
} for m in selected])
```

## Ranking Factors

### Relevance Score

How well the memory matches the query:

- **FTS**: BM25 or similar term frequency scoring
- **Vector**: Cosine similarity of embeddings
- **Combined**: Weighted average of both

### Recency Score

How recently the memory was created:

```python
days_old = (now - memory.created_at).days
recency_score = 1 / (1 + log(1 + days_old))
```

Newer memories score higher.

### Importance Score

User or AI-assigned importance:

```python
# Explicit importance
importance_score = memory.importance_score  # 0-1

# Or derived
if memory.memory_type == "preference":
    importance_score = 0.9
elif memory.memory_type == "observation":
    importance_score = 0.5
```

### Retrieval Frequency

How often a memory has been retrieved:

```python
# Promote frequently accessed memories
frequency_score = min(memory.retrieval_count / 10, 1.0)

# But also boost newly relevant memories
if memory.last_retrieved_at is None:
    novelty_score = 1.0
```

### Confidence Score

How certain the AI was when creating the memory:

```python
confidence_weight = 0.1  # Small weight
confidence_score = memory.confidence
```

## Context Budgeting

Managing token usage for memories:

### Item Limit

Hard limit on number of memories:

```python
max_items = 5  # Never include more than 5 memories
```

### Token Limit

Soft limit based on estimated tokens:

```python
max_tokens = 1000

# Approximate: 1 token ≈ 4 characters for English
text_length = sum(len(m.summary) for m in selected)
estimated_tokens = text_length / 4
```

### Priority-Based Selection

Select memories by priority when budget is tight:

```python
priority_order = [
    "profile",       # User identity (highest)
    "preference",    # User preferences
    "plan",          # Current plans
    "fact",          # Relevant facts
    "insight",       # Derived insights
    "observation",   # Observations
    "domain_object", # Structured objects
    "session_state"  # Temporary state (lowest)
]
```

## Advanced Retrieval

### Filtered Search

Search with specific constraints:

```python
search_memories(
    query="budget",
    filters={
        "memory_type": "fact",
        "scope_type": "user",
        "created_after": "2026-01-01",
        "min_confidence": 0.8
    }
)
```

### Temporal Queries

Handle time-based queries:

```python
# Query: "What did we discuss yesterday?"
temporal_resolution = resolve_temporal("yesterday")
# Returns: (2026-03-27 00:00:00, 2026-03-27 23:59:59)

search_memories(
    query="discuss",
    time_range=temporal_resolution
)
```

### Multi-hop Retrieval

Follow chains of related memories:

```python
# Find initial memory
project_memory = search_memories("current project")

# Find related memories
team_memories = search_memories(
    query=project_memory.data["team_members"],
    related_to=project_memory.id
)
```

## Memory Tools

### memory_search

```python
{
    "name": "memory_search",
    "description": "Search for relevant memories",
    "parameters": {
        "query": {
            "type": "string",
            "description": "What to search for"
        },
        "memory_type": {
            "type": "string",
            "enum": ["fact", "preference", "plan", ...],
            "description": "Optional filter by memory type"
        },
        "limit": {
            "type": "integer",
            "default": 5,
            "description": "Maximum results to return"
        }
    }
}
```

### memory_create

```python
{
    "name": "memory_create",
    "description": "Create a new memory",
    "parameters": {
        "title": {"type": "string"},
        "content": {"type": "string"},
        "memory_type": {"type": "string"},
        "importance": {"type": "number", "minimum": 0, "maximum": 1}
    }
}
```

### memory_update

```python
{
    "name": "memory_update",
    "description": "Update an existing memory",
    "parameters": {
        "memory_id": {"type": "string"},
        "updates": {"type": "object"}
    }
}
```

## Troubleshooting Retrieval

### Memories Not Found

| Symptom | Cause | Solution |
|---------|-------|----------|
| No results for valid query | Index not built | Wait for indexing or rebuild |
| Results missing | Wrong scope | Check scope_type and scope_key |
| Old memories missing | TTL expired | Check expiration settings |
| Specific memory not found | Status not active | Check memory status |

### Too Many/Irrelevant Results

| Symptom | Cause | Solution |
|---------|-------|----------|
| Unrelated memories | Query too vague | Make query more specific |
| Low-quality results | Low confidence threshold | Increase min_confidence |
| Duplicates | Multiple similar memories | Enable merge/deduplication |

### Performance Issues

| Symptom | Cause | Solution |
|---------|-------|----------|
| Slow search | Large index | Add filters, use FTS only |
| High token usage | Too many memories | Reduce max_items/max_tokens |
| Timeout | Complex query | Simplify query, add timeouts |

## Best Practices

1. **Start with Hybrid Mode**: Best balance of convenience and control
2. **Set Conservative Budgets**: Begin with 3-5 memories, 500-1000 tokens
3. **Use Filters**: Narrow search scope for better performance
4. **Monitor Retrieval**: Track which memories are used most
5. **Iterate on Ranking**: Adjust ranking weights based on results

## Next Steps

- See [Best Practices](./best-practices.md) for production tips
- Review [API Reference](./api-reference.md) for implementation details
- Learn about [Profiles](./profiles.md) for schema design