# Subagent Task: storage-indexing

## Mission
Implement storage backends and indexing infrastructure for Memory Records.

## Input Files (READ THESE FIRST)
- `~/code/huf-memory/tech_specs/STORAGE_ARCHITECTURE.md` - Storage specification
- `~/code/huf-memory/doctype_designs/memory_record.json` - Record structure with indexing fields
- `~/code/huf-memory/doctype_designs/memory_policy.json` - Storage configuration

## Deliverables

### 1. Storage Backend Abstraction
Create: `huf/huf/memory/storage/backends.py`

Abstract base class and implementations:

```python
class StorageBackend(ABC):
    @abstractmethod
    def store(self, memory_record) -> str: ...
    
    @abstractmethod
    def retrieve(self, record_id) -> dict: ...
    
    @abstractmethod
    def update(self, record_id, data) -> bool: ...
    
    @abstractmethod
    def delete(self, record_id) -> bool: ...
    
    @abstractmethod
    def search(self, query, filters) -> list: ...
```

### 2. Canonical Storage Implementation
Create: `huf/huf/memory/storage/canonical_storage.py`

Class `CanonicalStorage`:
- Uses Frappe DocType as source of truth
- All Memory Records stored in `tabMemory Record`
- Methods: `create()`, `update()`, `delete()`, `get_by_scope()`, `get_by_agent()`
- Handles JSON serialization for `data_json` field
- Manages soft delete (status = 'archived')

### 3. FTS (Full-Text Search) Backend
Create: `huf/huf/memory/storage/fts_backend.py`

Class `SQLiteFTSBackend`:
- Creates FTS5 virtual table: `memory_record_fts`
- Columns: `record_id`, `title`, `summary_text`, `raw_context_excerpt`, `data_text`
- Methods:
  - `index(memory_record)` - Add to FTS index
  - `reindex(record_id)` - Update existing index
  - `remove(record_id)` - Remove from index
  - `search(query, limit=10)` - Full-text search
  - `search_with_filters(query, filters)` - Filtered search
- Trigger integration: auto-update on record changes

### 4. Vector Backend
Create: `huf/huf/memory/storage/vector_backend.py`

Class `SQLiteVectorBackend`:
- Uses sqlite-vec extension (if available)
- Table: `memory_record_vectors`
- Columns: `record_id`, `embedding`, `model_name`, `created_at`
- Methods:
  - `index(memory_record, embedding)` - Store vector
  - `get_embedding(text)` - Call embedding model
  - `similarity_search(query_embedding, top_k=10)` - Vector similarity
  - `hybrid_search(query, query_embedding, top_k=10)` - FTS + vector
  - `delete(record_id)` - Remove vector
- Graceful fallback if sqlite-vec unavailable

### 5. Index Manager
Create: `huf/huf/memory/storage/index_manager.py`

Class `IndexManager`:
- Orchestrates indexing across backends
- Methods:
  - `index_record(memory_record)` - Index in all enabled backends
  - `reindex_record(record_id)` - Reindex single record
  - `reindex_all()` - Batch reindex everything
  - `get_backend(backend_name)` - Get backend instance
  - `is_backend_available(backend_name)` - Check availability
- Reads policy configuration for which backends to use
- Updates `last_indexed_at` on Memory Record

### 6. Embedding Service
Create: `huf/huf/memory/storage/embedding_service.py`

Class `EmbeddingService`:
- Methods:
  - `generate_embedding(text, model=None)` - Call embedding API
  - `batch_generate(texts)` - Efficient batch processing
  - `get_available_models()` - List configured models
- Support multiple providers: OpenAI, local models, etc.
- Caching layer for repeated texts

### 7. Database Migrations
Create: `huf/huf/patches/` files:
- `create_memory_fts_table.py` - FTS5 virtual table creation
- `create_memory_vector_table.py` - Vector table creation
- `add_memory_indexes.py` - Add performance indexes

### 8. Storage Configuration
Create: `huf/huf/memory/storage/config.py`

Settings:
- `DEFAULT_INDEX_BACKEND` - Default indexing mode
- `FTS_ENABLED` - Enable/disable FTS
- `VECTOR_ENABLED` - Enable/disable vector
- `EMBEDDING_MODEL` - Default embedding model
- `EMBEDDING_DIMENSIONS` - Vector dimensions

## Index Schema Details

### FTS5 Virtual Table
```sql
CREATE VIRTUAL TABLE memory_record_fts USING fts5(
    record_id,
    title,
    summary_text,
    raw_context_excerpt,
    data_text,
    content='memory_record',
    content_rowid='name'
);
```

### Vector Table
```sql
CREATE TABLE memory_record_vectors (
    record_id VARCHAR(255) PRIMARY KEY,
    embedding BLOB,  -- Serialized vector
    model_name VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Commits Required
1. `feat(memory): implement canonical storage backend`
2. `feat(memory): implement SQLite FTS indexing backend`
3. `feat(memory): implement SQLite vector indexing backend`
4. `feat(memory): implement index manager and orchestration`
5. `feat(memory): add embedding service with provider support`
6. `feat(memory): add database migrations for indexing tables`

## Success Criteria
- Canonical storage stores/retrieves Memory Records correctly
- FTS search returns relevant results
- Vector similarity search works (if sqlite-vec available)
- Index manager maintains `last_indexed_at` timestamps
- Graceful degradation when optional backends unavailable
- Reindexing works for single records and bulk operations