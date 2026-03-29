# Subagent Task: retrieval-system

## Mission
Implement memory retrieval system with prompt injection and search tools.

## Input Files (READ THESE FIRST)
- `~/code/huf-memory/tech_specs/CAPTURE_RETRIEVAL.md` - Retrieval specification
- `~/code/huf-memory/doctype_designs/memory_record.json` - Record structure
- `~/code/huf-memory/PRD.md` - Sections 13-15 (Scope, Storage, Retrieval)

## Deliverables

### 1. Retrieval Engine
Create: `huf/huf/memory/retrieval/engine.py`

Class `MemoryRetrievalEngine`:
- Main entry point for all retrieval operations
- Methods:
  - `retrieve_for_context(agent, conversation, query=None)` - Main retrieval
  - `search(query, filters, limit=10)` - Direct search
  - `get_by_scope(scope_type, scope_key)` - Scope-filtered retrieval
  - `get_recent(agent, limit=5)` - Recent memories
  - `get_important(agent, min_score=0.7)` - High importance memories

### 2. Scope-Aware Filtering
Create: `huf/huf/memory/retrieval/scope_filter.py`

Class `ScopeFilter`:
- Builds scope hierarchy for retrieval
- Methods:
  - `get_scope_chain(conversation)` - Get ordered list of scopes to check
  - `apply_scope_filter(query, scope_type, scope_key)` - Filter by scope
  - `can_access(record, requesting_agent, requesting_user)` - Permission check
- Scope hierarchy (most specific to least):
  1. conversation
  2. user
  3. namespace (if applicable)
  4. agent
  5. global

### 3. Prompt Injection System
Create: `huf/huf/memory/retrieval/prompt_injection.py`

Class `PromptInjectionBuilder`:
- Builds memory context for agent prompts
- Methods:
  - `build_memory_context(agent, conversation, max_tokens)` - Main builder
  - `format_memories_for_prompt(memories)` - Format as text
  - `inject_into_system_prompt(system_prompt, memory_context)` - Merge prompts
  - `calculate_token_budget(memories, max_tokens)` - Budget-aware selection
- Ranking algorithm: recency × confidence × importance × relevance

### 4. Memory Search Tool
Create: `huf/huf/memory/retrieval/search_tool.py`

Frappe Tool definition for agents:

```python
class MemorySearchTool:
    """Tool for agents to search their memory."""
    
    def search_memory(
        self,
        query: str,
        scope: str = "auto",  # auto, conversation, user, agent, global
        memory_type: str = None,
        limit: int = 5,
        min_confidence: float = 0.5
    ) -> dict:
        """
        Search memory records matching the query.
        
        Args:
            query: Search query text
            scope: Which scope to search
            memory_type: Filter by memory type
            limit: Maximum results
            min_confidence: Minimum confidence threshold
            
        Returns:
            Dict with results array and metadata
        """
```

### 5. Hybrid Retrieval
Create: `huf/huf/memory/retrieval/hybrid_retrieval.py`

Class `HybridRetrieval`:
- Combines FTS and vector search
- Methods:
  - `hybrid_search(query, query_embedding, weights)` - Combine scores
  - `reciprocal_rank_fusion(results_fts, results_vector, k=60)` - RRF algorithm
  - `weighted_merge(results, weights)` - Weighted score combination
- Configurable weights for FTS vs vector relevance

### 6. Relevance Ranking
Create: `huf/huf/memory/retrieval/ranking.py`

Class `RelevanceRanker`:
- Scoring algorithms:
  - `score_recency(created_at)` - Time decay score
  - `score_confidence(confidence)` - Confidence weighting
  - `score_importance(importance_score)` - Importance weighting
  - `score_retrieval_history(retrieval_count)` - Popular items boost
- Combined scoring: `calculate_final_score(memory, query_relevance)`

### 7. Memory Write Tool
Create: `huf/huf/memory/retrieval/write_tool.py`

Class `MemoryWriteTool`:
```python
def write_memory(
    self,
    title: str,
    data: dict,
    memory_type: str = "custom",
    scope: str = "conversation",
    confidence: float = 1.0
) -> dict:
    """
    Write a new memory record.
    
    Args:
        title: Memory title
        data: Structured data (JSON-serializable)
        memory_type: Type of memory
        scope: Visibility scope
        confidence: Confidence level (0-1)
        
    Returns:
        Created memory record metadata
    """
```

### 8. Retrieval Mode Handlers
Create: `huf/huf/memory/retrieval/modes.py`

Implement three retrieval modes:

#### Inject Mode
- Automatically inject relevant memories into system prompt
- Configurable max items and token budget
- Happens before agent execution

#### Tool-Only Mode
- No automatic injection
- Agent must explicitly call `search_memory` tool
- Full control by agent

#### Hybrid Mode (default)
- Top-N most relevant memories auto-injected
- Additional memories available via tool search
- Balanced approach

### 9. Agent Integration Hook
Modify: `huf/huf/agent/runner.py` or equivalent

Add to agent execution flow:
```python
# Before agent execution
if agent.enable_memory:
    memory_context = retrieval_engine.get_memory_context(agent, conversation)
    system_prompt = prompt_injection.inject(system_prompt, memory_context)

# Register tools
if agent.enable_memory_search_tool:
    tools.append(MemorySearchTool())
if agent.enable_memory_write_tool:
    tools.append(MemoryWriteTool())
```

### 10. Update Retrieval Stats
Create: `huf/huf/memory/retrieval/stats_tracker.py`

Class `RetrievalStatsTracker`:
- Updates `last_retrieved_at` on Memory Record
- Increments `retrieval_count`
- Batches updates for performance

## Retrieval API Endpoints

Create: `huf/huf/api/memory.py`

Endpoints:
- `GET /api/method/huf.memory.api.search` - Search memories
- `GET /api/method/huf.memory.api.get_by_scope` - Get by scope
- `POST /api/method/huf.memory.api.write` - Write memory
- `GET /api/method/huf.memory.api.recent` - Recent memories
- `GET /api/method/huf.memory.api.important` - Important memories

## Commits Required
1. `feat(memory): implement scope-aware filtering system`
2. `feat(memory): implement prompt injection builder`
3. `feat(memory): implement memory search tool for agents`
4. `feat(memory): implement hybrid retrieval with FTS+vector`
5. `feat(memory): implement memory write tool`
6. `feat(memory): integrate retrieval into agent execution flow`

## Success Criteria
- Memories can be retrieved by scope hierarchy
- Prompt injection adds relevant context to agent prompts
- `search_memory` tool returns accurate results
- `write_memory` tool creates valid Memory Records
- Hybrid mode balances auto-injection with tool access
- Retrieval stats are tracked accurately