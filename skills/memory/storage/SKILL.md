# Skill: Memory Storage

Work with storage backends and indexing for memory records.

## Overview

The memory system separates **canonical storage** (source of truth in MariaDB) from **optional indexing** (FTS, vector for retrieval acceleration).

## Storage Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    CANONICAL STORAGE                             │
│                    (MariaDB - DocType)                           │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Memory Record DocType                                   │    │
│  │  - name, title, data_json                                │    │
│  │  - scope_type, scope_key                                 │    │
│  │  - status, ttl, confidence                               │    │
│  └─────────────────────────────────────────────────────────┘    │
│                         │                                        │
│                         ▼                                        │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Optional Indexing (per-record policy)                  │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
   ┌──────────┐        ┌──────────┐        ┌──────────┐
   │   FTS    │        │  Vector  │        │  Hybrid  │
   │ (SQLite) │        │ (sqlite- │        │  (FTS +  │
   │          │        │   vec)   │        │  Vector) │
   └──────────┘        └──────────┘        └──────────┘
```

## Canonical Storage

**Location**: `huf/huf/memory/storage.py`

### MemoryRecord Class

Type-safe data class representing a memory record:

```python
from huf.memory.storage import MemoryRecord, SourceType, ProducerMode
from huf.memory.storage import MemoryType, ScopeType, Visibility, MemoryStatus

record = MemoryRecord(
    name="MEM-xxx",  # Auto-generated if not provided
    title="User Preference: Dark Mode",
    data_json={"theme": "dark", "contrast": "high"},
    agent="my-agent",
    conversation="conv_123",
    source_type=SourceType.CONVERSATION,
    producer_mode=ProducerMode.MAIN_AGENT,
    memory_type=MemoryType.PREFERENCE,
    scope_type=ScopeType.USER,
    scope_key="user@example.com",
    visibility=Visibility.PRIVATE,
    status=MemoryStatus.ACTIVE,
    confidence=0.95,
    importance_score=0.8,
    ttl_days=365,
    tags=["ui", "preference"],
    enable_fts_index=True,
    enable_vector_index=False
)

# Convert to Frappe Document
doc = record.to_doc()
doc.insert()

# From existing document
record = MemoryRecord.from_doc(doc)
```

### MemoryStorage Class

Primary interface for CRUD operations:

```python
from huf.memory.storage import get_storage, MemoryRecord

storage = get_storage()

# Create
record = MemoryRecord(title="...", data_json={...})
storage.create(record, index_callback=my_indexer)

# Read
record = storage.get("MEM-xxx")

# Update
record.title = "New Title"
storage.update(record, index_callback=my_indexer)

# Delete
storage.delete("MEM-xxx", index_callback=my_deleter)

# List with filters
records = storage.list(
    filters={"memory_type": "preference", "status": "active"},
    limit=50
)

# Find by scope
records = storage.find_by_scope(
    scope_type=ScopeType.USER,
    scope_key="user@example.com",
    memory_type=MemoryType.PREFERENCE
)

# Find by agent
records = storage.find_by_agent(agent="my-agent")

# Find by conversation
records = storage.find_by_conversation(conversation="conv_123")

# Find by tags
records = storage.find_by_tags(
    tags=["preference", "ui"],
    match_all=True  # Must have all tags
)

# Expire old records
expired_count = storage.expire_old_records()

# Get statistics
stats = storage.get_stats()
# Returns:
# {
#     "total_records": 100,
#     "active_records": 85,
#     "by_scope_type": {"user": 60, "conversation": 25},
#     "by_memory_type": {"preference": 40, "fact": 30},
#     "fts_indexed": 70,
#     "vector_indexed": 30
# }
```

## Index Backends

**Location**: `huf/huf/memory/backends.py`

### SQLite FTS5 Backend

Full-text search using SQLite FTS5:

```python
from huf.memory.backends import SQLiteFTSBackend

fts = SQLiteFTSBackend()

# Initialize (creates virtual table)
await fts.initialize()

# Index a record
result = await fts.index(record)
# Returns: IndexResult(success=True, record_id="...", backend="sqlite_fts")

# Search
results = await fts.search(
    query="dark mode preference",
    scope=ScopeFilter(scope_type="user", scope_key="user@example.com"),
    limit=10
)
# Returns: [SearchResult(record_id="...", score=1.2, snippet="...")]

# Delete from index
await fts.delete("MEM-xxx")

# Reindex
await fts.reindex(record)

# Clear all
await fts.clear()

# Check availability
available = fts.is_available()
```

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

### sqlite-vec Backend

Vector similarity search:

```python
from huf.memory.backends import SqliteVecBackend
from huf.memory.indexing import EmbeddingGenerator

# With embedding generator
vec = SqliteVecBackend(
    embedding_generator=EmbeddingGenerator(),
    dimension=1536  # Default for OpenAI embeddings
)

# Initialize
await vec.initialize()

# Index (requires embedding)
result = await vec.index(record)

# Search (generates query embedding automatically)
results = await vec.search(
    query="user interface preferences",
    scope=ScopeFilter(scope_type="user"),
    limit=10
)
# Returns results ranked by L2 distance (converted to similarity score)
```

**Schema**:
```sql
CREATE VIRTUAL TABLE memory_vec_idx USING vec0(
    record_id TEXT PRIMARY KEY,
    embedding FLOAT[1536]
);
```

### Hybrid Backend

Combines FTS + vector with Reciprocal Rank Fusion:

```python
from huf.memory.backends import HybridBackend, SQLiteFTSBackend, SqliteVecBackend

fts = SQLiteFTSBackend()
vec = SqliteVecBackend()

hybrid = HybridBackend(
    backends=[fts, vec],
    rrf_k=60,
    weights={"sqlite_fts": 0.4, "sqlite_vec": 0.6}
)

await hybrid.initialize()

# Index to all backends
result = await hybrid.index(record)

# Search with fusion
results = await hybrid.search(
    query="dark mode",
    scope=ScopeFilter(),
    limit=10
)
# Results fused using RRF: score = Σ weight_i / (k + rank_i)
```

### Backend Factory

```python
from huf.memory.backends import get_backend_for_policy

# Get appropriate backend based on policy
backend = get_backend_for_policy(
    enable_fts=True,
    enable_vector=True,
    vector_backend_type="sqlite_vec"
)
# Returns: HybridBackend, SQLiteFTSBackend, SqliteVecBackend, or NoOpBackend
```

## Indexing

**Location**: `huf/huf/memory/indexing.py`

### MemoryIndexBackend (Abstract)

Base class for all backends:

```python
from huf.memory.indexing import MemoryIndexBackend, IndexResult, SearchResult

class MyBackend(MemoryIndexBackend):
    async def index(self, record) -> IndexResult:
        pass
    
    async def search(self, query, scope, limit) -> list[SearchResult]:
        pass
    
    async def delete(self, record_id) -> bool:
        pass
    
    async def reindex(self, record) -> IndexResult:
        pass
```

### EmbeddingGenerator

```python
from huf.memory.indexing import EmbeddingGenerator

generator = EmbeddingGenerator(
    model="text-embedding-3-small",
    provider="openai"
)

# Generate embedding
embedding = await generator.generate("User prefers dark mode interface")
# Returns: [0.023, -0.045, ...] (1536 dimensions)

# Batch generate
embeddings = await generator.generate_batch([
    "Dark mode preference",
    "English language",
    "GMT timezone"
])
```

### ScopeFilter

```python
from huf.memory.indexing import ScopeFilter

scope = ScopeFilter(
    scope_type="user",
    scope_key="user@example.com",
    agent="my-agent",
    memory_type="preference"
)
```

## Configuration Examples

### Minimal (No Indexing)

```json
{
    "enable_fts_index": false,
    "enable_vector_index": false,
    "index_backend": "none"
}
```

Use case: Development, low-resource deployments, privacy-sensitive records.

### FTS Only

```json
{
    "enable_fts_index": true,
    "enable_vector_index": false,
    "fts_backend": "sqlite_fts"
}
```

Use case: Keyword-heavy domains (CRM, support tickets), no semantic search needed.

### Vector Only

```json
{
    "enable_fts_index": false,
    "enable_vector_index": true,
    "vector_backend": "sqlite_vec"
}
```

Use case: Semantic similarity search, moderate scale.

### Hybrid (Recommended)

```json
{
    "enable_fts_index": true,
    "enable_vector_index": true,
    "vector_backend": "sqlite_vec",
    "index_backend": "sqlite_fts"
}
```

Use case: Best retrieval quality, combines keyword + semantic.

## Database Schema

### Memory Record Table

| Column | Type | Description |
|--------|------|-------------|
| name | VARCHAR(140) | Primary key |
| title | VARCHAR(140) | Human-readable |
| data_json | JSON | Structured payload |
| scope_type | VARCHAR(50) | conversation, user, agent, namespace, global |
| scope_key | VARCHAR(140) | Scope identifier |
| memory_type | VARCHAR(50) | Type classification |
| status | VARCHAR(50) | active, superseded, archived, expired |
| confidence | DECIMAL(3,2) | 0.0-1.0 |
| importance_score | DECIMAL(3,2) | 0.0-1.0 |
| fts_indexed | TINYINT(1) | FTS index status |
| vector_indexed | TINYINT(1) | Vector index status |

## Best Practices

1. **Always use canonical storage** - It's the source of truth
2. **Index asynchronously** - Don't block user responses
3. **Choose backends based on need**:
   - Keyword-heavy → FTS
   - Semantic similarity → Vector
   - Best quality → Hybrid
4. **Monitor index lag** - Track `last_indexed_at` vs `modified`
5. **Graceful degradation** - Handle missing extensions gracefully
6. **Regular cleanup** - Expire old records to save space
