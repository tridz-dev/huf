# HUF Agent Memory System

> **Location**: `huf/huf/memory/`  
> **Status**: Implemented (MVP Complete)  
> **Last Updated**: 2026-03-28

---

## Table of Contents

1. [Overview](#1-overview)
2. [Core Concepts](#2-core-concepts)
3. [Architecture](#3-architecture)
4. [DocTypes](#4-doctypes)
5. [Capture Modes](#5-capture-modes)
6. [Triggers](#6-triggers)
7. [Retrieval](#7-retrieval)
8. [Storage Backends](#8-storage-backends)
9. [Memory Tools](#9-memory-tools)
10. [Agent Integration](#10-agent-integration)
11. [Configuration Examples](#11-configuration-examples)
12. [API Reference](#12-api-reference)

---

## 1. Overview

The HUF Agent Memory System is a **first-class, configurable memory and learning layer** that enables agents to maintain durable, scoped, portable memory and reusable learned knowledge over time.

### Key Capabilities

- **Structured capture** - Extract and store memories as structured JSON records
- **Multiple capture modes** - In-prompt, post-run sync/async, specialized agents, or rule-based
- **Flexible scoping** - Conversation, user, agent, namespace, or global scope
- **Pluggable storage** - Canonical MariaDB storage with optional FTS5 and vector indexing
- **Three retrieval modes** - Inject, tool-only, or hybrid
- **Opinionated profiles** - Pre-built profiles for programming, travel, CRM, documentation

### Comparison: Old vs New

| Aspect | Old "Data Management" | New Memory System |
|--------|----------------------|-------------------|
| Storage | Conversation-embedded JSON | First-class Memory Record DocType |
| Capture | Manual/prompt-driven | 5 configurable capture modes |
| Scope | Implicit | Explicit (5 scope types) |
| Indexing | None | FTS5, sqlite-vec, pgvector (future) |
| Retrieval | Ad-hoc | Inject, tool-only, hybrid |
| Profiles | None | 5+ built-in profiles |

---

## 2. Core Concepts

### 2.1 Memory Record
The canonical portable unit of memory. A structured or semi-structured object produced from conversation, run, event, or post-run process.

### 2.2 Memory Policy
Defines **how** an agent performs memory capture - the capture mode, frequency, schema, quality thresholds, and storage backends.

### 2.3 Memory Profile
Opinionated presets providing default schemas, prompts, and configuration for common domains (programming, travel, CRM, etc.).

### 2.4 Capture Mode
Defines **who** performs extraction and **when** during the request lifecycle.

### 2.5 Trigger
Defines **when** capture is executed based on lifecycle events.

### 2.6 Retrieval Mode
Defines **how** memory is accessed during agent execution.

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     AGENT EXECUTION                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   Trigger    │───▶│   Capture    │───▶│   Memory     │       │
│  │   System     │    │   Mode       │    │   Record     │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│         │                   │                   │                │
│         │                   │                   ▼                │
│         │                   │            ┌──────────────┐       │
│         │                   │            │   Canonical  │       │
│         │                   │            │   Storage    │       │
│         │                   │            │   (MariaDB)  │       │
│         │                   │            └──────┬───────┘       │
│         │                   │                   │                │
│         │                   │                   ▼                │
│         │                   │            ┌──────────────┐       │
│         │                   └───────────▶│   Indexing   │       │
│         │                                │   (FTS/Vec)  │       │
│         │                                └──────────────┘       │
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   Retrieval  │◀───│    Search    │◀───│   Backend    │       │
│  │    Mode      │    │              │    │   (FTS/Vec)  │       │
│  └──────┬───────┘    └──────────────┘    └──────────────┘       │
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────┐    ┌──────────────┐                           │
│  │   Prompt     │───▶│    Agent     │                           │
│  │   Injection  │    │   Response   │                           │
│  └──────────────┘    └──────────────┘                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. DocTypes

### 4.1 Memory Record

**File**: `huf/huf/doctype/memory_record/`

| Field | Type | Description |
|-------|------|-------------|
| `title` | Data | Human-readable summary |
| `agent` | Link | → Agent |
| `conversation` | Link | → Agent Conversation |
| `run` | Link | → Agent Run |
| `source_type` | Select | conversation, run, manual, event, scheduled, imported |
| `producer_mode` | Select | main_agent, memory_agent, post_run_llm, rules_only, manual |
| `memory_type` | Select | profile, session_state, preference, fact, plan, observation, insight, domain_object, custom |
| `schema_name` | Data | JSON schema identifier |
| `profile_name` | Link | → Memory Profile |
| `data_json` | JSON | Structured payload (canonical) |
| `summary_text` | Text | Human-readable summary for display/FTS |
| `raw_context_excerpt` | Long Text | Original context snapshot |
| `scope_type` | Select | conversation, user, agent, namespace, global |
| `scope_key` | Data | Scope identifier |
| `visibility` | Select | private, shared_with_agent, shared_with_namespace, global |
| `status` | Select | active, superseded, archived, expired, error |
| `confidence` | Float | 0.0-1.0 extraction confidence |
| `importance_score` | Float | 0.0-1.0 ranking weight |
| `ttl_days` | Int | Auto-expiry duration |
| `effective_from` | Datetime | Validity start |
| `effective_until` | Datetime | Validity end |
| `supersedes_memory_record` | Link | → Memory Record (version chain) |
| `fts_indexed` | Check | FTS index status |
| `vector_indexed` | Check | Vector index status |
| `index_backend` | Select | none, sqlite_fts, sqlite_vec, pgvector, custom |
| `retrieval_count` | Int | Usage counter |

### 4.2 Memory Policy

**File**: `huf/huf/doctype/memory_policy/`

| Field | Type | Description |
|-------|------|-------------|
| `policy_name` | Data | Unique identifier |
| `enabled` | Check | Whether policy is active |
| `agent` | Link | → Agent (optional) |
| `memory_profile` | Link | → Memory Profile |
| `capture_owner` | Select | main_agent, memory_agent, post_run_llm, rules_only |
| `memory_agent` | Link | → Agent (for specialized_agent mode) |
| `capture_stage` | Select | in_prompt, post_response_sync, post_response_async, conversation_end, scheduled |
| `capture_frequency_type` | Select | every_run, every_n_runs, every_n_turns, conversation_end, manual, scheduled |
| `capture_frequency_value` | Int | N value for frequency |
| `capture_prompt` | Long Text | Instructions for extraction |
| `capture_schema_json` | JSON | Schema for validation |
| `allow_open_schema` | Check | Allow unstructured capture |
| `min_confidence` | Float | Minimum confidence threshold |
| `retrieval_mode_default` | Select | inject, tool_only, hybrid |
| `max_items_to_inject` | Int | Hard limit on injected memories |
| `max_tokens_to_inject` | Int | Soft token budget |
| `enable_fts_index` | Check | Enable FTS indexing |
| `enable_vector_index` | Check | Enable vector indexing |
| `vector_backend` | Select | sqlite_vec, pgvector |

### 4.3 Memory Profile

**File**: `huf/huf/doctype/memory_profile/`

| Field | Type | Description |
|-------|------|-------------|
| `profile_name` | Data | Unique identifier |
| `description` | Small Text | Human-readable description |
| `category` | Data | Category for grouping |
| `default_schema_json` | JSON | Schema for this profile |
| `default_capture_prompt` | Long Text | Profile-specific capture instructions |
| `recommended_model` | Link | → AI Model |
| `recommended_provider` | Link | → AI Provider |
| `default_capture_stage` | Select | Default capture timing |
| `default_scope_type` | Select | Default scope |
| `default_indexing_mode` | Select | fts, vector, both |
| `default_retrieval_mode` | Select | inject, tool_only, hybrid |
| `is_system_profile` | Check | System-provided vs custom |

**Built-in Profiles**:
- **Programming Memory** - Code patterns, conventions, debugging
- **General Knowledge Memory** - Facts, preferences, habits
- **Travel Planning Memory** - Destinations, dates, preferences
- **CRM Memory** - Customer context, interactions
- **Documentation Memory** - Requirements, decisions, API contracts

---

## 5. Capture Modes

**Location**: `huf/huf/memory/capture.py`

### 5.1 In-Prompt Capture (`in_prompt`)

| Attribute | Value |
|-----------|-------|
| Execution Phase | During main agent inference |
| Latency Impact | Zero (part of main request) |
| Producer | Main agent |

**Implementation**: Memory instructions prepended to system prompt. Agent outputs memory updates as part of JSON response.

**Best for**: Low-latency session state, simple preference updates

### 5.2 Post-Response Synchronous (`post_sync`)

| Attribute | Value |
|-----------|-------|
| Execution Phase | After main response, before returning to user |
| Latency Impact | High (blocks user response) |
| Producer | Main agent or memory agent |

**Implementation**: Capture prompt + conversation context sent to extraction model. Memory committed synchronously.

**Best for**: Critical profile updates, highly structured extractions

### 5.3 Post-Response Asynchronous (`post_async`) ⭐ Recommended

| Attribute | Value |
|-----------|-------|
| Execution Phase | Background job after user response |
| Latency Impact | Zero (non-blocking) |
| Producer | Main agent, memory agent, or post-run processor |

**Implementation**: Capture job enqueued to RQ/background queue. Eventual consistency.

**Best for**: Travel capture, CRM enrichment, learned summaries

### 5.4 Specialized Memory Agent (`specialized_agent`)

| Attribute | Value |
|-----------|-------|
| Execution Phase | Configurable (sync or async) |
| Latency Impact | Varies |
| Producer | Dedicated memory agent instance |

**Implementation**: Separate Agent record with specialized prompt. May use cheaper/faster model.

**Best for**: Strict schemas, domain-specific extraction, cost optimization

### 5.5 Rule-Only Capture (`rules_only`)

| Attribute | Value |
|-----------|-------|
| Execution Phase | Deterministic (sync) |
| Latency Impact | Minimal (no LLM call) |
| Producer | Rule engine |

**Implementation**: No LLM. Fields populated from context values, regex, tool outputs.

**Rule Types**:
- `static` - Fixed value assignment
- `context` - Extract from conversation context
- `regex` - Pattern match on messages
- `tool` - Capture from tool outputs
- `computed` - Derived from other fields

**Best for**: Exact identifiers, timestamps, state transitions

---

## 6. Triggers

**Location**: `huf/huf/memory/triggers.py`

| Trigger | Description |
|---------|-------------|
| `every_run` | Every agent run/turn |
| `every_n_runs` | Every N runs (configurable) |
| `every_n_turns` | Every N turns in conversation |
| `after_tool_call` | After specific tool execution |
| `final_response_only` | Only on final assistant response |
| `conversation_end` | When conversation marked complete |
| `idle_timeout` | After inactivity threshold |
| `manual` | Explicit user/admin trigger |
| `scheduled` | Cron-based consolidation |

### End Detection Strategies

- `manual_close` - User/admin explicitly closes
- `idle_timeout` - No activity for N minutes
- `heuristic` - Agent classifies conversation as complete
- `workflow_complete` - Workflow reaches terminal state

---

## 7. Retrieval

**Location**: `huf/huf/memory/retrieval.py`

### 7.1 Inject Mode

Memory auto-injected into system prompt at conversation start/before each run.

```markdown
## Relevant Memory

### Profile: User Preferences
- Language: English
- Timezone: America/New_York

### Session: Travel Planning
- Destination: Tokyo
- Dates: 2024-05-01 to 2024-05-10
```

### 7.2 Tool-Only Mode

No automatic injection. Agent must call `memory_search` tool.

### 7.3 Hybrid Mode ⭐ Recommended

Top-K high-priority memory auto-injected. Full memory search tool also available. Injected memory IDs excluded from tool results.

### Retrieval Ranking

```
score = importance_score × 0.4 + 
        recency_weight × 0.3 + 
        scope_relevance × 0.2 + 
        (1 / (1 + retrieval_count)) × 0.1
```

---

## 8. Storage Backends

**Location**: `huf/huf/memory/backends.py`

### 8.1 Canonical Storage (MariaDB)

All memory lives in `Memory Record` DocType. Source of truth, always queryable.

### 8.2 SQLite FTS5 Backend

Full-text search using SQLite FTS5 virtual tables:
- Porter stemming
- Unicode61 tokenization
- Contentless design (joins to canonical)

**Schema**:
```sql
CREATE VIRTUAL TABLE memory_fts_idx USING fts5(
    record_id UNINDEXED,
    title,
    summary_text,
    data_json,
    tags,
    tokenize='porter unicode61'
);
```

### 8.3 sqlite-vec Backend

Semantic similarity search using sqlite-vec extension:
- Default 1536 dimensions
- L2 distance or cosine similarity

**Schema**:
```sql
CREATE VIRTUAL TABLE memory_vec_idx USING vec0(
    record_id TEXT PRIMARY KEY,
    embedding FLOAT[1536]
);
```

### 8.4 Hybrid Backend

Combines FTS + vector with Reciprocal Rank Fusion (RRF):

```
score = Σ weight_i / (k + rank_i)
```

Default k=60.

---

## 9. Memory Tools

**Location**: `huf/huf/memory/retrieval/memory_search_tool.py`

### 9.1 memory_search

```python
memory_search(
    query: str = None,                    # Search text
    memory_type: str = None,             # Filter by type
    memory_types: List[str] = None,      # Filter by multiple types
    scope_type: str = None,              # conversation, user, agent, namespace, global
    tags: List[str] = None,              # Filter by tags
    min_confidence: float = None,        # 0.0-1.0
    min_importance: float = None,        # 0.0-1.0
    limit: int = 10,                     # Max results
    offset: int = 0,                     # Pagination
)
```

Returns:
```python
{
    "success": True,
    "memories": [...],
    "total_found": 3,
    "query": "user preferences"
}
```

### 9.2 memory_get_recent

Get recently created memories ordered by creation time.

### 9.3 memory_get_by_type

Get memories filtered by specific type.

### 9.4 memory_get_by_scope

Get memories within a specific scope.

---

## 10. Agent Integration

### 10.1 Agent DocType Fields

New Memory section fields:

| Field | Type | Description |
|-------|------|-------------|
| `enable_memory` | Check | Enable memory system |
| `memory_policy` | Link | → Memory Policy |
| `memory_profile` | Link | → Memory Profile |
| `default_memory_scope_type` | Select | Default scope |
| `memory_retrieval_mode` | Select | inject, tool_only, hybrid |
| `memory_in_prompt_budget` | Int | Token budget for injection |
| `enable_memory_search_tool` | Check | Add memory_search tool |
| `enable_memory_write_tool` | Check | Add memory_write tool |
| `memory_agent` | Link | → Agent for specialized capture |
| `memory_max_items` | Int | Max memories to inject |

### 10.2 Agent Run Observability

| Field | Type | Description |
|-------|------|-------------|
| `memory_capture_triggered` | Check | Whether capture ran |
| `memory_capture_mode` | Data | Capture mode used |
| `memory_records_created` | Int | Records created |
| `memory_records_updated` | Int | Records updated |
| `memory_records_skipped` | Int | Records skipped |
| `memory_capture_latency_ms` | Int | Capture latency |

### 10.3 Integration Flow

```
1. Before agent execution:
   → build_memory_context_for_agent() retrieves relevant memories

2. Prompt preparation:
   → inject_memory_into_prompt() adds memory context

3. Agent execution:
   → Agent can call memory_search tool (if enabled)

4. After agent response:
   → capture_memory() processes capture based on policy
   → Creates/updates Memory Record
   → Queues indexing jobs
   → Updates run observability fields
```

---

## 11. Configuration Examples

### 11.1 Minimal (No Indexing)

```json
{
  "enable_fts_index": false,
  "enable_vector_index": false,
  "index_backend": "none"
}
```

### 11.2 FTS Only

```json
{
  "enable_fts_index": true,
  "enable_vector_index": false,
  "fts_backend": "sqlite_fts"
}
```

### 11.3 Vector Only (sqlite-vec)

```json
{
  "enable_fts_index": false,
  "enable_vector_index": true,
  "vector_backend": "sqlite_vec",
  "index_backend": "sqlite_vec"
}
```

### 11.4 Hybrid (Recommended)

```json
{
  "enable_fts_index": true,
  "enable_vector_index": true,
  "vector_backend": "sqlite_vec",
  "index_backend": "sqlite_fts"
}
```

### 11.5 Use Case Configurations

| Use Case | Capture Mode | Trigger | Retrieval |
|----------|--------------|---------|-----------|
| Session state | `in_prompt` | `every_run` | `inject` |
| User profile | `post_sync` | `every_n_runs` | `inject` |
| Travel capture | `specialized_agent` | `conversation_end` | `hybrid` |
| CRM enrichment | `post_async` | `after_tool_call` | `tool_only` |
| Learning/insights | `specialized_agent` | `every_n_turns` | `hybrid` |
| System events | `rules_only` | `manual` | `inject` |

---

## 12. API Reference

### 12.1 Retrieval Functions

```python
# Get available retrieval modes
huf.memory.retrieval.get_retrieval_modes()

# Test retrieval with mode
huf.memory.retrieval.test_retrieval(
    mode: str,
    agent_name: str,
    query: str = None
)
```

### 12.2 Injection Functions

```python
# Preview what memory context would be injected
huf.memory.injection.preview_memory_context(
    agent_name: str,
    conversation_id: str = None,
    query: str = None
)

# Test memory injection with sample prompt
huf.memory.injection.test_memory_injection(
    prompt: str,
    agent_name: str,
    conversation_id: str = None
)
```

### 12.3 Capture Functions

```python
# Manual capture
huf.memory.processor.capture_memory(
    context: Dict,
    policy_config: Dict = None,
    force: bool = False
)

# Async capture
huf.memory.processor.capture_memory_async(
    context: Dict,
    policy_config: Dict = None
)

# Conversation end capture
huf.memory.processor.process_conversation_end(
    conversation_id: str,
    policy_config: Dict = None
)
```

### 12.4 Storage Functions

```python
from huf.memory.storage import get_storage, MemoryRecord

storage = get_storage()

# Create record
record = MemoryRecord(
    title="User Preference",
    data_json={"theme": "dark"},
    memory_type=MemoryType.PREFERENCE,
    scope_type=ScopeType.USER
)
storage.create(record)

# Get by ID
record = storage.get("MEM-xxx")

# Find by scope
records = storage.find_by_scope(
    scope_type=ScopeType.USER,
    scope_key="user@example.com"
)
```

---

## 13. File Structure

```
huf/huf/memory/
├── __init__.py                 # Package exports
├── capture.py                  # Capture mode classes (5 modes)
├── capture/
│   ├── __init__.py
│   ├── capture_service.py
│   ├── in_prompt_capture.py
│   ├── post_run_capture.py
│   ├── memory_agent_capture.py
│   └── rule_capture.py
├── triggers.py                 # Trigger classes (9 types)
├── processor.py                # CaptureProcessor orchestration
├── storage.py                  # MemoryStorage + MemoryRecord class
├── retrieval.py                # Retrieval mode classes (3 modes)
├── retrieval/
│   ├── __init__.py
│   ├── retrieval_service.py
│   ├── memory_search_tool.py   # Agent tools
│   ├── memory_write_tool.py
│   └── prompt_injector.py
├── injection.py                # Prompt injection
├── search.py                   # MemorySearcher with ranking
├── indexing.py                 # Index backend abstraction
├── backends.py                 # FTS, vector, hybrid backends
└── storage/                    # Storage backend implementations
    ├── __init__.py
    ├── index_backend.py
    ├── fts_indexer.py
    └── vector_indexer.py
```

---

## 14. Related Documentation

- **PRD.md** - Product Requirements Document
- **tech_specs/CAPTURE_RETRIEVAL.md** - Capture & Retrieval Technical Specs
- **tech_specs/STORAGE_ARCHITECTURE.md** - Storage Architecture
- **IMPLEMENTATION_PLAN.md** - Implementation roadmap

---

*For more information, see the [HUF AGENTS.md](../AGENTS.md) file.*
