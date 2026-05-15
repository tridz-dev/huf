# Capture & Retrieval Technical Specifications

This document specifies the technical implementation for HUF's memory capture modes, trigger system, and retrieval model.

---

## 1. Capture Modes

Capture modes define **who performs the extraction** and **when** during the request lifecycle.

### 1.1 In-Prompt Capture

| Attribute | Specification |
|-----------|---------------|
| **Mode ID** | `in_prompt` |
| **Execution Phase** | During main agent inference |
| **Latency Impact** | Zero (part of main request) |
| **Producer** | Main agent |

**Implementation:**
- Memory instructions are prepended to the main agent system prompt
- Agent outputs memory updates as part of its JSON response structure
- Memory fields are extracted from the response and committed synchronously
- Schema validation occurs post-response before write

**Best For:**
- Low-latency session state tracking
- Simple preference updates
- Domain-specific fields where prompt engineering is mature

**Configuration:**
```json
{
  "capture_mode": "in_prompt",
  "capture_prompt": "System instructions for what to extract...",
  "schema_json": { "type": "object", "properties": {...} },
  "require_json_schema_match": true,
  "allow_open_schema": false
}
```

---

### 1.2 Post-Response Synchronous Capture

| Attribute | Specification |
|-----------|---------------|
| **Mode ID** | `post_response_sync` |
| **Execution Phase** | After main response, before returning to user |
| **Latency Impact** | High (blocks user response) |
| **Producer** | Main agent or memory agent |

**Implementation:**
- Main agent response is returned to controller
- Capture prompt + conversation context is sent to extraction model
- Memory record is created/updated synchronously
- User receives response only after memory commit succeeds

**Flow:**
```
User Input → Main Agent → Response Ready → Extract Memory → Commit → Return to User
```

**Best For:**
- Critical profile updates requiring consistency
- Highly structured extractions with strict schemas
- Low-volume, high-importance memory types

**Configuration:**
```json
{
  "capture_mode": "post_response_sync",
  "capture_agent": null,
  "timeout_seconds": 10,
  "fallback_on_error": "skip"
}
```

---

### 1.3 Post-Response Asynchronous Capture

| Attribute | Specification |
|-----------|---------------|
| **Mode ID** | `post_response_async` |
| **Execution Phase** | Background job after user response sent |
| **Latency Impact** | Zero (non-blocking) |
| **Producer** | Main agent, memory agent, or post-run processor |

**Implementation:**
- User response is returned immediately
- Capture job is enqueued to background queue (RQ/background job)
- Job runs with conversation context snapshot
- Memory record creation is eventual consistency
- Failure is logged but does not block user

**Flow:**
```
User Input → Main Agent → Return Response → Queue Capture Job → Process Async
```

**Best For:**
- Travel/itinerary capture
- CRM enrichment
- Long conversation summarization
- Learned insight extraction
- Default mode for most profiles

**Configuration:**
```json
{
  "capture_mode": "post_response_async",
  "capture_agent": "memory-extractor-v1",
  "queue_name": "memory_capture",
  "retry_count": 3,
  "max_context_turns": 20
}
```

---

### 1.4 Specialized Memory Agent

| Attribute | Specification |
|-----------|---------------|
| **Mode ID** | `specialized_agent` |
| **Execution Phase** | Configurable (sync or async) |
| **Latency Impact** | Varies by execution phase |
| **Producer** | Dedicated memory agent instance |

**Implementation:**
- Memory agent is a separate Agent record with specialized prompt
- May use cheaper/faster model optimized for extraction
- Receives conversation context + extraction instructions
- Returns structured memory payload
- Can run sync or async depending on trigger

**Agent Configuration:**
- `is_memory_agent: true` — marks agent as special-purpose
- Optimized system prompt for extraction tasks
- Optional model override (e.g., gpt-4o-mini for cost efficiency)
- Fixed output schema via response_format

**Best For:**
- Strict schema compliance
- Domain-specific extraction requiring different reasoning
- Cost optimization (cheaper model for extraction)
- Separation of concerns (main agent focuses on user, memory agent on storage)

**Configuration:**
```json
{
  "capture_mode": "specialized_agent",
  "memory_agent": "extractor-agent-uuid",
  "execution_timing": "post_response_async",
  "pass_full_history": true,
  "pass_summary_only": false
}
```

---

### 1.5 Rule-Only Capture

| Attribute | Specification |
|-----------|---------------|
| **Mode ID** | `rules_only` |
| **Execution Phase** | Deterministic (sync) |
| **Latency Impact** | Minimal (no LLM call) |
| **Producer** | Rule engine |

**Implementation:**
- No LLM inference for extraction
- Memory fields populated from:
  - Exact context values (user_id, timestamp, state flags)
  - Regex/template extractions
  - Tool call outputs
  - System event payloads
- JSON Path or Jinja2 template mapping
- Direct commit to memory record

**Rule Types:**
1. **Static:** Fixed value assignment
2. **Context:** Extract from conversation/run context
3. **Regex:** Pattern match on user/agent messages
4. **Tool:** Capture tool inputs/outputs
5. **Computed:** Derived from other fields

**Best For:**
- Exact identifiers (user_id, conversation_id)
- Timestamps and versioning
- State transitions (ticket opened → closed)
- System-generated plans/events
- Deterministic metadata capture

**Configuration:**
```json
{
  "capture_mode": "rules_only",
  "rules": [
    { "field": "user_id", "source": "context", "path": "user.id" },
    { "field": "captured_at", "source": "static", "value": "{{ now() }}" },
    { "field": "intent", "source": "regex", "pattern": "book.*flight", "on_match": "flight_booking" }
  ]
}
```

---

## 2. Trigger System

Triggers define **when** capture is executed. Each trigger maps to a lifecycle event.

### 2.1 Trigger Types

| Trigger ID | Description | Execution Timing |
|------------|-------------|------------------|
| `every_run` | Every agent run/turn | Post-response |
| `every_n_runs` | Every N runs (configurable) | Post-response |
| `every_n_turns` | Every N turns in conversation | Post-response |
| `after_tool_call` | After specific tool execution | Post-tool |
| `final_response_only` | Only on final assistant response | Post-response |
| `conversation_end` | When conversation is marked complete | End event |
| `idle_timeout` | After inactivity threshold | Background job |
| `manual` | Explicit user/admin trigger | On-demand |
| `scheduled` | Cron-based consolidation | Scheduled job |

---

### 2.2 Every Run

**Trigger ID:** `every_run`

**Implementation:**
- Fire after every non-error agent response
- Configurable debounce (min_seconds_between)
- Deduplication via hash of context snapshot

**Use Cases:**
- Session state tracking
- Continuous preference learning
- High-granularity observation capture

---

### 2.3 Every N Runs

**Trigger ID:** `every_n_runs`

**Implementation:**
- Counter maintained on Agent Run record
- Fire when `run_count % N == 0`
- Counter resets per conversation or global (configurable)

**Parameters:**
```json
{
  "trigger_type": "every_n_runs",
  "frequency_value": 5,
  "counter_scope": "conversation"
}
```

**Use Cases:**
- Periodic summarization
- Batch insight extraction
- Reducing capture frequency for cost control

---

### 2.4 Every N Turns

**Trigger ID:** `every_n_turns`

**Implementation:**
- Counter maintained on Agent Conversation record
- Fire when `turn_count % N == 0`
- Turn counting includes user + assistant exchanges

**Parameters:**
```json
{
  "trigger_type": "every_n_turns",
  "frequency_value": 10,
  "count_both_roles": true
}
```

**Use Cases:**
- Chunked conversation summarization
- Progressive profile building
- Milestone-based capture

---

### 2.5 After Tool Call

**Trigger ID:** `after_tool_call`

**Implementation:**
- Registered tool names trigger capture
- Tool input/output included in context
- Fire after tool completes, before final response

**Parameters:**
```json
{
  "trigger_type": "after_tool_call",
  "watched_tools": ["search_flights", "book_hotel"],
  "capture_tool_output": true
}
```

**Use Cases:**
- Structured booking capture after travel tool use
- CRM updates after customer lookup
- State capture after significant actions

---

### 2.6 Final Response Only

**Trigger ID:** `final_response_only`

**Implementation:**
- Fire only on assistant message (not tool calls)
- Skip intermediate tool-turns in multi-step runs

**Use Cases:**
- Summary capture only
- Reducing noise from tool-only turns
- Final state capture for workflows

---

### 2.7 Conversation End

**Trigger ID:** `conversation_end`

**Implementation:**
- Triggered by conversation state change to `ended`
- Can be synchronous or queued for processing
- Always captures full conversation context

**End Detection Strategies:**

| Strategy | Detection Method |
|----------|------------------|
| `manual_close` | User/admin explicitly closes conversation |
| `idle_timeout` | No activity for `idle_timeout_minutes` |
| `heuristic` | Agent classifies conversation as complete |
| `workflow_complete` | Workflow reaches terminal state |

**Configuration:**
```json
{
  "trigger_type": "conversation_end",
  "end_strategy": "idle_timeout",
  "idle_timeout_minutes": 30,
  "capture_full_summary": true
}
```

**Use Cases:**
- Final summarization
- Complete profile extraction
- Conversation archival
- Post-conversation analytics

---

### 2.8 Idle Timeout

**Trigger ID:** `idle_timeout`

**Implementation:**
- Background job checks for idle conversations
- Fire on timeout (conversation not explicitly closed)
- May auto-close conversation or just capture state

**Configuration:**
```json
{
  "trigger_type": "idle_timeout",
  "idle_timeout_minutes": 30,
  "auto_close_on_timeout": true,
  "capture_before_close": true
}
```

**Use Cases:**
- Capturing abandoned conversations
- Session cleanup with memory preservation
- Timeout-based state snapshots

---

### 2.9 Manual Trigger

**Trigger ID:** `manual`

**Implementation:**
- Explicit API endpoint `/api/memory/capture`
- UI button "Capture Memory Now"
- Admin/operator initiated

**Parameters:**
```json
{
  "trigger_type": "manual",
  "conversation_id": "conv_xxx",
  "capture_mode": "specialized_agent"
}
```

**Use Cases:**
- On-demand capture
- Admin override
- Testing and debugging

---

### 2.10 Scheduled Consolidation

**Trigger ID:** `scheduled`

**Implementation:**
- Cron-based trigger via HUF scheduler
- Processes batches of memory records
- Typically used for Phase 2+ operations (merge, dedupe)

**Configuration:**
```json
{
  "trigger_type": "scheduled",
  "cron_expression": "0 2 * * *",
  "operation": "consolidate",
  "scope_filter": { "memory_type": "observation" }
}
```

**Use Cases:**
- Daily memory consolidation
- Batch deduplication
- Expiry and pruning
- Reflection and synthesis

---

### 2.11 Trigger Selection Matrix

| If you need... | Use Trigger |
|----------------|-------------|
| Always capture | `every_run` |
| Cost-conscious periodic capture | `every_n_runs` / `every_n_turns` |
| Action-driven capture | `after_tool_call` |
| Summary only | `final_response_only` |
| Complete conversation capture | `conversation_end` |
| Handle abandonment | `idle_timeout` |
| On-demand | `manual` |
| Batch processing | `scheduled` |

---

## 3. Retrieval Model

The retrieval model defines **how memory is accessed** during agent execution.

### 3.1 Retrieval Modes

| Mode ID | Description |
|---------|-------------|
| `inject` | Memory auto-injected into system prompt |
| `tool_only` | Agent must call tool to query memory |
| `hybrid` | Top-K memory injected + full search via tool |

---

### 3.2 Inject Mode

**Mode ID:** `inject`

**Implementation:**
- Query memory store at conversation start and/or before each run
- Format results as structured context block
- Prepend to system prompt (before knowledge, after core instructions)

**Query Construction:**
```python
filters = {
    "scope_type": policy.scope_type,
    "scope_key": resolve_scope_key(policy, conversation),
    "memory_type": policy.memory_types or None,
    "status": "active",
    "effective_date": "<= now"
}
results = memory_store.search(
    filters=filters,
    order_by=["-importance_score", "-last_retrieved_at", "-created_at"],
    limit=policy.max_items_to_inject
)
```

**Context Format:**
```markdown
## Relevant Memory

### Profile: User Preferences
- Language: English
- Timezone: America/New_York

### Session: Travel Planning
- Destination: Tokyo
- Dates: 2024-05-01 to 2024-05-10
```

**Budgeting:**
- `max_items_to_inject`: Hard limit on memory records
- `max_tokens_to_inject`: Soft limit via token estimation
- Priority ranking: importance_score × recency_weight × retrieval_count_decay

**Best For:**
- High-priority profile data
- Small, stable context sets
- Latency-sensitive applications

---

### 3.3 Tool-Only Mode

**Mode ID:** `tool_only`

**Implementation:**
- No automatic injection
- Memory search tool available to agent
- Agent explicitly queries when needed

**Tool Definition:**
```json
{
  "name": "memory_search",
  "description": "Search memory records for relevant context",
  "parameters": {
    "query": "Search query text",
    "memory_type": "Optional filter by type",
    "scope": "conversation|user|agent|global",
    "limit": 10,
    "min_confidence": 0.5
  }
}
```

**Tool Response:**
```json
{
  "results": [
    {
      "memory_id": "mem_xxx",
      "title": "User prefers formal tone",
      "data": { "tone_preference": "formal" },
      "confidence": 0.95,
      "source_conversation": "conv_xxx"
    }
  ]
}
```

**Best For:**
- Large memory corpora
- Rarely-needed historical data
- Memory as secondary knowledge source
- Agent-controlled retrieval strategy

---

### 3.4 Hybrid Mode

**Mode ID:** `hybrid`

**Implementation:**
- Top-K high-priority memory auto-injected
- Full memory search tool also available
- Injected memory marked to avoid double-retrieval

**Configuration:**
```json
{
  "retrieval_mode": "hybrid",
  "inject": {
    "max_items": 5,
    "selection": "highest_importance"
  },
  "tool": {
    "enabled": true,
    "default_limit": 10
  },
  "deduplicate": true
}
```

**Deduplication:**
- Injected memory IDs passed to tool context
- Tool excludes already-injected IDs from results
- Or tool results include `already_injected` flag

**Best For:**
- Balanced approach
- Profile injection + searchable archive
- Most general-purpose configuration

---

### 3.5 Retrieval Filters

All retrieval modes support filtering:

| Filter | Description |
|--------|-------------|
| `scope_type` | conversation / user / agent / namespace / global |
| `scope_key` | Specific scope identifier |
| `agent` | Source agent filter |
| `user` | Source user filter |
| `memory_type` | profile / preference / fact / plan / observation / insight / domain_object |
| `profile_name` | Specific memory profile |
| `tags` | Array match (any or all) |
| `status` | active / superseded / archived / expired |
| `min_confidence` | Confidence threshold |
| `min_importance` | Importance threshold |
| `created_after` | Recency filter |
| `effective_date` | Current validity filter |
| `source_type` | conversation / run / manual / event / scheduled |

---

### 3.6 Retrieval Ranking (Phase 1)

**Base Score:**
```
score = importance_score × 0.4 + 
        recency_weight × 0.3 + 
        scope_relevance × 0.2 + 
        (1 / (1 + retrieval_count)) × 0.1
```

**Components:**
- `importance_score`: 0.0-1.0, explicit or derived
- `recency_weight`: exponential decay from creation date
- `scope_relevance`: exact match = 1.0, parent scope = 0.8, global = 0.5
- `retrieval_count_decay`: penalize over-fetched items

**Backend Relevance:**
- FTS: BM25 score normalized
- Vector: cosine similarity
- Hybrid: weighted combination

---

### 3.7 Configuration Summary

```json
{
  "retrieval": {
    "mode": "hybrid",
    "inject": {
      "max_items": 5,
      "max_tokens": 2000,
      "order_by": ["-importance_score", "-created_at"]
    },
    "tool": {
      "enabled": true,
      "default_limit": 10,
      "max_limit": 100
    },
    "filters": {
      "default_status": ["active"],
      "default_scope": "inherit_from_conversation"
    }
  }
}
```

---

## 4. Mode + Trigger + Retrieval Combinations

### Recommended Configurations

| Use Case | Capture Mode | Trigger | Retrieval |
|----------|--------------|---------|-----------|
| Session state | `in_prompt` | `every_run` | `inject` |
| User profile | `post_response_sync` | `every_n_runs` | `inject` |
| Travel capture | `specialized_agent` + async | `conversation_end` | `hybrid` |
| CRM enrichment | `post_response_async` | `after_tool_call` | `tool_only` |
| Learning/insights | `specialized_agent` + async | `every_n_turns` | `hybrid` |
| System events | `rules_only` | `manual` | `inject` |
| Documentation | `post_response_async` | `conversation_end` | `tool_only` |

---

## 5. Implementation Notes

### Priority Order

1. **Mode** determines **who extracts**
2. **Trigger** determines **when** extraction runs
3. **Retrieval** determines **how** memory is consumed

### Error Handling

| Mode | Error Behavior |
|------|----------------|
| `in_prompt` | Validation error → skip, log warning |
| `post_response_sync` | Configurable: skip / retry / fail request |
| `post_response_async` | Queue retry with backoff, alert after N failures |
| `specialized_agent` | Same as sync/async depending on timing |
| `rules_only` | Hard error (no LLM fallback), log and skip |

### Observability

All capture operations log:
- `capture_mode`
- `trigger_type`
- `latency_ms`
- `records_created`
- `records_updated`
- `tokens_consumed`
- `error` (if any)

To Agent Run: `memory_capture_triggered`, `memory_capture_mode`, `memory_records_created`, `memory_capture_latency_ms`
