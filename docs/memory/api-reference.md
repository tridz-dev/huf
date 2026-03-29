# API Reference

Complete reference for the HUF Memory System APIs.

## Python API

### Core Module: `huf.huf.memory`

#### `capture_memory()`

Extract and store a memory from conversation context.

```python
from huf.huf.memory.capture import capture_memory

result = capture_memory(
    agent="support-bot",
    conversation="CONV-2026-001",
    context={
        "messages": [...],
        "metadata": {...}
    },
    policy="default-conservative",
    profile="crm"
)

# Returns
{
    "success": True,
    "memory_id": "MREC-2026-03-28-00001",
    "title": "Customer interested in enterprise plan",
    "confidence": 0.92
}
```

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `agent` | str | Yes | Agent name creating the memory |
| `conversation` | str | Yes | Conversation ID |
| `context` | dict | Yes | Conversation context with messages |
| `policy` | str | No | Memory policy to use |
| `profile` | str | No | Memory profile to use |
| `run` | str | No | Agent run ID |

**Returns**: Dict with `success`, `memory_id`, `title`, `confidence`

---

#### `search_memories()`

Search for memories with various filters.

```python
from huf.huf.memory.search import search_memories

results = search_memories(
    query="user preferences",
    agent="support-bot",
    scope_type="user",
    scope_key="user_123",
    memory_types=["preference", "profile"],
    limit=10,
    search_mode="hybrid"
)

# Returns list of MemoryRecord objects
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | str | - | Search query string |
| `agent` | str | None | Filter by agent |
| `scope_type` | str | None | Filter by scope type |
| `scope_key` | str | None | Filter by scope key |
| `memory_types` | list | None | Filter by memory types |
| `limit` | int | 10 | Maximum results |
| `search_mode` | str | "hybrid" | "fts", "vector", or "hybrid" |
| `min_confidence` | float | None | Minimum confidence threshold |
| `created_after` | datetime | None | Filter by creation date |

**Returns**: List of `MemoryRecord` objects

---

#### `get_memory_context()`

Get formatted memory context for injection into prompts.

```python
from huf.huf.memory.retrieval import get_memory_context

context = get_memory_context(
    agent="support-bot",
    conversation="CONV-2026-001",
    user="user_123",
    query="current issues",
    max_items=5,
    max_tokens=1000
)

# Returns formatted string for prompt injection
"Relevant memories:\n• User reported login issues yesterday\n• User prefers email communication\n..."
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `agent` | str | Yes | Agent name |
| `conversation` | str | Yes | Conversation ID |
| `user` | str | Yes | User ID |
| `query` | str | None | Contextual query for relevance |
| `max_items` | int | 5 | Maximum memories to include |
| `max_tokens` | int | 1000 | Token budget |
| `memory_types` | list | None | Filter by types |

**Returns**: Formatted string ready for prompt injection

---

#### `create_memory()`

Programmatically create a memory record.

```python
from huf.huf.memory.storage import create_memory

memory = create_memory(
    title="User preference for dark mode",
    memory_type="preference",
    data={"theme": "dark", "reason": "easier on eyes"},
    agent="support-bot",
    scope_type="user",
    scope_key="user_123",
    confidence=0.95,
    importance=0.8
)

# Returns MemoryRecord object
```

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `title` | str | Yes | Memory title |
| `memory_type` | str | Yes | Type of memory |
| `data` | dict | Yes | Structured memory data |
| `agent` | str | Yes | Agent name |
| `scope_type` | str | Yes | Scope type |
| `scope_key` | str | Yes | Scope identifier |
| `confidence` | float | No | Confidence score (0-1) |
| `importance` | float | No | Importance score (0-1) |
| `summary` | str | No | Text summary |
| `conversation` | str | No | Conversation ID |

**Returns**: `MemoryRecord` object

---

#### `update_memory()`

Update an existing memory.

```python
from huf.huf.memory.storage import update_memory

updated = update_memory(
    memory_id="MREC-2026-03-28-00001",
    updates={
        "data": {"theme": "dark", "accent": "blue"},
        "importance": 0.9
    },
    merge=True  # Merge with existing data
)
```

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `memory_id` | str | Yes | Memory record ID |
| `updates` | dict | Yes | Fields to update |
| `merge` | bool | No | Merge data dict (default: False) |

**Returns**: Updated `MemoryRecord` object

---

#### `delete_memory()`

Delete or archive a memory.

```python
from huf.huf.memory.storage import delete_memory

# Soft delete (archive)
delete_memory("MREC-2026-03-28-00001", hard_delete=False)

# Hard delete
delete_memory("MREC-2026-03-28-00001", hard_delete=True)
```

---

#### `get_memory()`

Retrieve a single memory by ID.

```python
from huf.huf.memory.storage import get_memory

memory = get_memory("MREC-2026-03-28-00001")
print(memory.title)
print(memory.data)
```

---

### Setup Module

#### `after_install()`

Hook called after app installation. Seeds default data.

```python
from huf.huf.memory.setup import after_install

# Called automatically by Frappe
after_install()
```

#### `after_migrate()`

Hook called after migration. Ensures default data exists.

```python
from huf.huf.memory.setup import after_migrate

# Called automatically by Frappe
after_migrate()
```

#### `seed_memory_profiles()`

Seed default memory profiles (idempotent).

```python
from huf.huf.memory.setup import seed_memory_profiles

seed_memory_profiles()
```

#### `seed_memory_policies()`

Seed default memory policies (idempotent).

```python
from huf.huf.memory.setup import seed_memory_policies

seed_memory_policies()
```

#### `get_seeding_stats()`

Get statistics about seeded data.

```python
from huf.huf.memory.setup import get_seeding_stats

stats = get_seeding_stats()
# {
#     "profiles": {"total_default": 7, "created": 7, "available": [...]},
#     "policies": {"total_default": 3, "created": 3, "available": [...]}
# }
```

---

### Indexing Module

#### `index_memory()`

Index a memory for search.

```python
from huf.huf.memory.indexing import index_memory

index_memory(
    memory_id="MREC-2026-03-28-00001",
    index_types=["fts", "vector"]
)
```

#### `search_index()`

Search the index directly.

```python
from huf.huf.memory.indexing import search_index

results = search_index(
    query="dark mode",
    index_type="hybrid",
    limit=10
)
```

#### `rebuild_index()`

Rebuild all indexes.

```python
from huf.huf.memory.indexing import rebuild_index

rebuild_index(index_type="all")
```

---

## DocType API

### Memory Record

Access Memory Records through Frappe's DocType API.

```python
import frappe

# Create
memory = frappe.new_doc("Memory Record")
memory.title = "User preference"
memory.memory_type = "preference"
memory.data_json = '{"theme": "dark"}'
memory.agent = "support-bot"
memory.scope_type = "user"
memory.scope_key = "user_123"
memory.insert()

# Read
memory = frappe.get_doc("Memory Record", "MREC-2026-03-28-00001")

# Update
memory.title = "Updated preference"
memory.save()

# Delete
frappe.delete_doc("Memory Record", "MREC-2026-03-28-00001")

# Query
memories = frappe.get_all(
    "Memory Record",
    filters={
        "agent": "support-bot",
        "status": "active",
        "scope_type": "user"
    },
    fields=["name", "title", "memory_type", "data_json"]
)
```

---

### Memory Profile

```python
import frappe

# Get all profiles
profiles = frappe.get_all("Memory Profile", fields=["*"])

# Get system profiles
system_profiles = frappe.get_all(
    "Memory Profile",
    filters={"is_system_profile": 1}
)

# Get profile by name
profile = frappe.get_doc("Memory Profile", "Programming")
print(profile.default_schema_json)
print(profile.default_capture_prompt)
```

---

### Memory Policy

```python
import frappe

# Get policy
policy = frappe.get_doc("Memory Policy", "Default Conservative")

# Check if enabled
if policy.enabled:
    print(f"Policy captures every {policy.capture_frequency_type}")

# Get policy for agent
agent_policies = frappe.get_all(
    "Memory Policy",
    filters={"agent": "support-bot", "enabled": 1}
)
```

---

## Frontend API

### React Hooks

#### `useMemory()`

Hook for memory operations.

```typescript
import { useMemory } from '@/hooks/useMemory';

function MyComponent() {
  const {
    memories,
    loading,
    error,
    searchMemories,
    createMemory,
    updateMemory,
    deleteMemory
  } = useMemory();

  // Search memories
  const handleSearch = async (query: string) => {
    await searchMemories({
      query,
      agent: 'support-bot',
      limit: 10
    });
  };

  // Create memory
  const handleCreate = async (data: MemoryData) => {
    await createMemory({
      title: data.title,
      memory_type: 'preference',
      data: data.content,
      agent: 'support-bot',
      scope_type: 'user',
      scope_key: 'user_123'
    });
  };

  return (
    // ...
  );
}
```

---

#### `useMemorySearch()`

Dedicated hook for searching.

```typescript
import { useMemorySearch } from '@/hooks/useMemorySearch';

function SearchComponent() {
  const { results, loading, search } = useMemorySearch({
    debounceMs: 300,
    minQueryLength: 2
  });

  return (
    <input
      onChange={(e) => search(e.target.value)}
      placeholder="Search memories..."
    />
  );
}
```

---

### API Client

#### `memoryApi.search()`

```typescript
import { memoryApi } from '@/services/api';

const results = await memoryApi.search({
  query: 'user preferences',
  agent: 'support-bot',
  scope_type: 'user',
  scope_key: 'user_123',
  limit: 10,
  search_mode: 'hybrid'
});
```

#### `memoryApi.create()`

```typescript
const memory = await memoryApi.create({
  title: 'New preference',
  memory_type: 'preference',
  data: { theme: 'dark' },
  agent: 'support-bot',
  scope_type: 'user',
  scope_key: 'user_123'
});
```

#### `memoryApi.update()`

```typescript
const updated = await memoryApi.update('MREC-2026-03-28-00001', {
  data: { theme: 'light' },
  importance: 0.9
});
```

#### `memoryApi.delete()`

```typescript
await memoryApi.delete('MREC-2026-03-28-00001');
```

#### `memoryApi.get()`

```typescript
const memory = await memoryApi.get('MREC-2026-03-28-00001');
```

---

### Types

```typescript
// types/memory.types.ts

interface MemoryRecord {
  name: string;
  title: string;
  memory_type: MemoryType;
  data_json: Record<string, any>;
  summary_text?: string;
  agent: string;
  conversation?: string;
  scope_type: ScopeType;
  scope_key: string;
  visibility: Visibility;
  confidence?: number;
  importance_score?: number;
  status: 'active' | 'superseded' | 'archived' | 'expired' | 'error';
  created_at: string;
  modified_at: string;
}

type MemoryType = 
  | 'profile' 
  | 'session_state' 
  | 'preference' 
  | 'fact' 
  | 'plan' 
  | 'observation' 
  | 'insight' 
  | 'domain_object' 
  | 'custom';

type ScopeType = 'conversation' | 'user' | 'agent' | 'namespace' | 'global';
type Visibility = 'private' | 'shared_with_agent' | 'shared_with_namespace' | 'global';

interface MemoryProfile {
  name: string;
  profile_name: string;
  description?: string;
  category: string;
  is_system_profile: boolean;
  default_schema_json: Record<string, any>;
  default_capture_prompt: string;
  default_capture_stage: CaptureStage;
  default_frequency: CaptureFrequency;
  default_scope_type: ScopeType;
  recommended_model?: string;
  recommended_provider?: string;
}

type CaptureStage = 
  | 'in_prompt' 
  | 'post_response_sync' 
  | 'post_response_async' 
  | 'conversation_end' 
  | 'scheduled';

type CaptureFrequency = 
  | 'every_run' 
  | 'every_n_runs' 
  | 'every_n_turns' 
  | 'conversation_end' 
  | 'manual' 
  | 'scheduled';

type CaptureOwner = 
  | 'main_agent' 
  | 'memory_agent' 
  | 'post_run_llm' 
  | 'rules_only';

type RetrievalMode = 'inject' | 'tool_only' | 'hybrid';

type IndexBackend = 
  | 'none' 
  | 'sqlite_fts' 
  | 'sqlite_vec' 
  | 'pgvector' 
  | 'custom';

interface MemoryPolicy {
  name: string;
  policy_name: string;
  enabled: boolean;
  description?: string;
  agent?: string;
  memory_profile?: string;
  capture_owner: CaptureOwner;
  memory_agent?: string;
  capture_stage: CaptureStage;
  capture_frequency_type: CaptureFrequency;
  capture_frequency_value?: number;
  conversation_end_strategy?: 'manual_close' | 'idle_timeout' | 'heuristic' | 'never';
  idle_timeout_minutes?: number;
  capture_prompt?: string;
  capture_schema_json?: Record<string, any>;
  allow_open_schema: boolean;
  require_json_schema_match: boolean;
  allow_update_existing: boolean;
  allow_merge: boolean;
  allow_append: boolean;
  min_confidence?: number;
  store_raw_payload: boolean;
  store_summary: boolean;
  enable_fts_index: boolean;
  enable_vector_index: boolean;
  vector_backend?: 'sqlite_vec' | 'pgvector' | 'custom';
  fts_backend?: 'sqlite_fts' | 'custom';
  retrieval_mode_default: RetrievalMode;
  max_items_to_inject?: number;
  max_tokens_to_inject?: number;
}

interface SearchParams {
  query: string;
  agent?: string;
  conversation?: string;
  scope_type?: ScopeType;
  scope_key?: string;
  memory_types?: MemoryType[];
  limit?: number;
  search_mode?: 'fts' | 'vector' | 'hybrid';
  min_confidence?: number;
  created_after?: string;
  created_before?: string;
}

interface CreateMemoryParams {
  title: string;
  memory_type: MemoryType;
  data: Record<string, any>;
  agent: string;
  scope_type: ScopeType;
  scope_key: string;
  summary?: string;
  conversation?: string;
  confidence?: number;
  importance?: number;
}
```

---

## REST API

### Authentication

All endpoints require Frappe authentication (Cookie or API Key).

### Endpoints

#### GET /api/resource/Memory Record

List memory records.

```bash
curl -X GET 'https://your-site.com/api/resource/Memory%20Record' \
  -H 'Authorization: token api_key:api_secret' \
  -G -d 'filters=[["agent", "=", "support-bot"]]' \
     -d 'fields=["name", "title", "memory_type"]'
```

#### POST /api/resource/Memory Record

Create a memory record.

```bash
curl -X POST 'https://your-site.com/api/resource/Memory%20Record' \
  -H 'Authorization: token api_key:api_secret' \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "User preference",
    "memory_type": "preference",
    "data_json": "{\"theme\": \"dark\"}",
    "agent": "support-bot",
    "scope_type": "user",
    "scope_key": "user_123"
  }'
```

#### GET /api/resource/Memory Record/{name}

Get a specific memory.

```bash
curl -X GET 'https://your-site.com/api/resource/Memory%20Record/MREC-2026-03-28-00001' \
  -H 'Authorization: token api_key:api_secret'
```

#### PUT /api/resource/Memory Record/{name}

Update a memory.

```bash
curl -X PUT 'https://your-site.com/api/resource/Memory%20Record/MREC-2026-03-28-00001' \
  -H 'Authorization: token api_key:api_secret' \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "Updated preference",
    "data_json": "{\"theme\": \"light\"}"
  }'
```

#### DELETE /api/resource/Memory Record/{name}

Delete a memory.

```bash
curl -X DELETE 'https://your-site.com/api/resource/Memory%20Record/MREC-2026-03-28-00001' \
  -H 'Authorization: token api_key:api_secret'
```

#### POST /api/method/huf.huf.memory.search.search_memories

Advanced search with hybrid ranking.

```bash
curl -X POST 'https://your-site.com/api/method/huf.huf.memory.search.search_memories' \
  -H 'Authorization: token api_key:api_secret' \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "user preferences",
    "agent": "support-bot",
    "search_mode": "hybrid",
    "limit": 10
  }'
```

---

## Error Handling

### Python Exceptions

```python
from huf.huf.memory.exceptions import (
    MemoryNotFoundError,
    InvalidMemoryDataError,
    CaptureError,
    IndexError
)

try:
    memory = create_memory(...)
except InvalidMemoryDataError as e:
    # Handle validation error
    print(f"Invalid data: {e}")
except CaptureError as e:
    # Handle capture failure
    print(f"Capture failed: {e}")
```

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad Request (invalid data) |
| 401 | Unauthorized (check auth) |
| 403 | Forbidden (permissions) |
| 404 | Not Found |
| 500 | Server Error |

---

## Rate Limiting

Memory operations may be rate-limited:

- Search: 100 requests/minute
- Create: 60 requests/minute
- Update: 60 requests/minute
- Delete: 30 requests/minute

Exceeding limits returns HTTP 429 (Too Many Requests).