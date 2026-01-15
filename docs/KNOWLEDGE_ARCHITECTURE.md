# Knowledge System Architecture & Design Decisions

## Overview

The Huf Knowledge System Phase 1 provides a portable, low-ops knowledge management system using SQLite Full-Text Search (FTS5). It follows the same abstraction philosophy as LiteLLM, positioning LlamaIndex as an integration layer rather than the architecture owner.

## Core Principles

### 1. Abstraction Over Implementation

**Decision**: Agents bind to **Knowledge Sources**, not databases or files.

**Rationale**:
- Enables backend switching without agent changes
- Maintains consistency with LiteLLM provider abstraction
- Allows future expansion to vector databases without refactoring

**Implementation**:
- `KnowledgeBackend` ABC defines the contract
- Agents call `knowledge_search()` function, not SQL directly
- Backend type (`sqlite_fts`) is configuration, not code

### 2. Frappe DB = Source of Truth

**Decision**: All metadata, permissions, and file references live in MariaDB.

**Rationale**:
- Leverages existing Frappe infrastructure
- Enables permission checks and audit trails
- Supports multi-tenant isolation
- SQLite files are derived artifacts, not primary storage

**Implementation**:
- `Knowledge Source` DocType stores configuration
- `Knowledge Input` DocType tracks ingestion
- SQLite files stored as private Frappe Files
- Can rebuild SQLite from Frappe data at any time

### 3. SQLite = Search Artifact

**Decision**: SQLite FTS5 files are derived, rebuildable artifacts.

**Rationale**:
- Portable (single file per source)
- No external dependencies (no vector DB servers)
- Fast keyword search with BM25 ranking
- Can be backed up/restored easily

**Implementation**:
- One SQLite file per Knowledge Source
- Stored in `/private/files/knowledge/`
- Fully rebuildable from Knowledge Inputs
- Atomic rebuilds (create `.tmp`, rename when done)

### 4. LlamaIndex as Integration Layer

**Decision**: Use LlamaIndex for text extraction and chunking, not as RAG framework.

**Rationale**:
- Reuse proven text extraction libraries
- Leverage sentence-aware chunking
- Future backend adapters (Chroma, pgvector) via LlamaIndex
- Keep architecture control within Huf

**What LlamaIndex Provides**:
- `SentenceSplitter` for intelligent chunking
- Text extraction utilities (via readers)
- Future: Vector store adapters

**What Huf Owns**:
- Knowledge lifecycle management
- Permissions and access control
- Agent binding and configuration
- Ingestion orchestration
- Prompt injection policy

## Architecture Layers

```
┌─────────────────────────────────────────────────────────┐
│                    Agent Layer                           │
│  (Agents use knowledge_search(), don't know about DBs) │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              Knowledge Abstraction Layer                 │
│  (knowledge_search contract, mandatory/optional modes)  │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│            LlamaIndex Integration Layer                  │
│  (Text extraction, chunking, future backend adapters)  │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                  Storage Backends                        │
│  Phase 1: SQLite FTS | Future: Chroma, pgvector, etc. │
└─────────────────────────────────────────────────────────┘
```

## Component Design

### Backend Abstraction

**Design**: Abstract base class (`KnowledgeBackend`) with concrete implementations.

**Why**:
- Enables pluggable backends
- Same interface for SQLite FTS, future Chroma, pgvector, etc.
- Agents don't change when backend changes

**Interface**:
```python
class KnowledgeBackend(ABC):
    def initialize(knowledge_source, config)
    def add_chunks(chunks) -> int
    def delete_chunks(input_id) -> int
    def search(query, top_k, filters) -> List[ChunkResult]
    def clear()
    def get_stats() -> Dict
```

### Text Extraction

**Design**: Pluggable extractors with fallback to plain text.

**Why**:
- Support multiple file formats
- Graceful degradation if libraries missing
- Easy to add new extractors

**Extractors**:
- PDF: PyPDF2/pypdf (optional dependency)
- DOCX: python-docx (optional dependency)
- HTML: BeautifulSoup (optional dependency)
- URL: requests + BeautifulSoup (optional dependency)
- Text: Built-in (always available)

**Fallback Strategy**:
- If specific extractor fails → fallback to text extractor
- If extraction fails → mark input as Error, don't crash system

### Chunking Strategy

**Design**: Sentence-aware chunking with LlamaIndex, fallback to simple chunking.

**Why**:
- Preserves sentence boundaries (better for search)
- Overlapping chunks maintain context
- Fallback ensures system works without LlamaIndex

**Configuration**:
- `chunk_size`: Default 512 characters
- `chunk_overlap`: Default 50 characters
- Per-knowledge-source configuration

**Future Enhancements**:
- Semantic chunking (by topic)
- Table-aware chunking
- Code-aware chunking

### Ingestion Pipeline

**Design**: Background jobs with Redis locking.

**Why**:
- Non-blocking (doesn't slow down UI)
- Safe concurrent access (single writer per source)
- Retryable on failure

**Flow**:
1. User creates Knowledge Input → Status: Pending
2. Background job triggered automatically
3. Acquire Redis lock for knowledge source
4. Extract text → Chunk → Insert SQLite
5. Update status → Release lock

**Locking Strategy**:
- Key: `knowledge_index_{source_name}`
- Expires: 300 seconds (5 minutes)
- Prevents concurrent writes to same source

### Retrieval System

**Design**: BM25-ranked search with multi-source support.

**Why**:
- BM25 is proven keyword ranking algorithm
- Fast (SQLite FTS5 optimized)
- No embeddings required (Phase 1)

**Search Flow**:
1. Agent calls `knowledge_search(query, source, top_k)`
2. Backend searches SQLite FTS5 with BM25
3. Results ranked by score
4. Return top_k chunks with metadata

**Multi-Source**:
- Can search multiple sources in one call
- Results combined and re-ranked
- Priority determines search order

### Knowledge Modes

**Design**: Mandatory (autoload) vs Optional (tool-based).

**Mandatory Mode**:
- Knowledge auto-injected into prompt before LLM call
- Agent cannot function without it
- Use case: Product documentation, company policies

**Optional Mode**:
- Agent decides when to search
- Uses `knowledge_search` tool
- Use case: Reference materials, FAQs

**Why Two Modes**:
- Different use cases need different access patterns
- Mandatory = always relevant, Optional = on-demand
- Token budget management (mandatory has limits)

## Data Flow

### Ingestion Flow

```
User Uploads File
       │
       ▼
Knowledge Input Created (Status: Pending)
       │
       ▼
Background Job Queued
       │
       ▼
Acquire Redis Lock
       │
       ▼
Extract Text (PDF/DOCX/HTML/Text/URL)
       │
       ▼
Chunk Text (SentenceSplitter)
       │
       ▼
Insert into SQLite (chunks + FTS5 index)
       │
       ▼
Update Knowledge Input (Status: Indexed)
       │
       ▼
Update Knowledge Source Stats
       │
       ▼
Release Redis Lock
```

### Retrieval Flow (Mandatory)

```
Agent Run Starts
       │
       ▼
Build Knowledge Context
       │
       ▼
For each Mandatory Source:
  - Search SQLite FTS5
  - Collect top chunks
       │
       ▼
Inject Context into Prompt
       │
       ▼
Call LLM Provider
       │
       ▼
Track Knowledge Usage in Agent Run
```

### Retrieval Flow (Optional)

```
Agent Decides to Search
       │
       ▼
Calls knowledge_search Tool
       │
       ▼
Search Optional Sources
       │
       ▼
Return Formatted Results
       │
       ▼
Agent Uses Results in Response
```

## Design Decisions

### Why SQLite FTS5 (Not Vectors)?

**Decision**: Phase 1 uses keyword search only, no embeddings.

**Rationale**:
- **Simplicity**: No embedding model required
- **Portability**: Single file, no external services
- **Speed**: FTS5 is fast for keyword search
- **Cost**: No embedding API costs
- **Future-proof**: Can add vectors later without breaking changes

**Trade-offs**:
- ✅ Pros: Simple, fast, portable, no dependencies
- ❌ Cons: No semantic similarity, keyword-only matching

**Future**: Phase 2 will add embeddings while keeping FTS5 as fallback.

### Why Background Jobs (Not Synchronous)?

**Decision**: Indexing happens in background jobs, not during save.

**Rationale**:
- **Non-blocking**: UI doesn't freeze on large files
- **Retryable**: Failed jobs can be retried
- **Scalable**: Can process multiple inputs in parallel
- **User Experience**: Immediate feedback, processing happens async

**Trade-offs**:
- ✅ Pros: Better UX, scalable, retryable
- ❌ Cons: Status tracking needed, eventual consistency

### Why Redis Locking (Not Database Locks)?

**Decision**: Use Redis for distributed locking during indexing.

**Rationale**:
- **Distributed**: Works across multiple workers
- **Fast**: Redis is fast for lock operations
- **Expiring**: Locks auto-expire if worker crashes
- **Simple**: No complex database locking logic

**Trade-offs**:
- ✅ Pros: Distributed, fast, auto-expiring
- ❌ Cons: Requires Redis (but Frappe already uses it)

### Why BM25 (Not TF-IDF)?

**Decision**: Use BM25 ranking algorithm for search results.

**Rationale**:
- **Better Ranking**: BM25 handles term frequency saturation better
- **Industry Standard**: Used by Elasticsearch, Solr, etc.
- **Built-in**: SQLite FTS5 supports BM25 natively
- **Proven**: Decades of research and production use

**Trade-offs**:
- ✅ Pros: Better relevance, standard algorithm, native support
- ❌ Cons: Still keyword-based (no semantic understanding)

### Why Sentence-Aware Chunking?

**Decision**: Use LlamaIndex SentenceSplitter instead of fixed-size chunks.

**Rationale**:
- **Better Context**: Preserves sentence boundaries
- **Search Quality**: Chunks are more coherent
- **Readability**: Results make more sense to users
- **Proven**: LlamaIndex has optimized chunking logic

**Trade-offs**:
- ✅ Pros: Better chunk quality, coherent results
- ❌ Cons: Slightly more complex, requires LlamaIndex

### Why Two Knowledge Modes?

**Decision**: Support both Mandatory (autoload) and Optional (tool) modes.

**Rationale**:
- **Different Use Cases**: Some knowledge always needed, some on-demand
- **Token Management**: Mandatory has token budgets, Optional is agent-controlled
- **Flexibility**: Agents can choose when to access optional knowledge
- **Performance**: Mandatory pre-loads, Optional searches only when needed

**Trade-offs**:
- ✅ Pros: Flexible, efficient, supports different patterns
- ❌ Cons: More complex configuration

## Extensibility

### Adding New Backends

To add a new backend (e.g., Chroma):

1. Create backend class implementing `KnowledgeBackend`
2. Register in `backends/__init__.py` → `get_backend()`
3. Add backend type to Knowledge Source options
4. Agents automatically work with new backend (no code changes)

### Adding New Extractors

To add a new file type:

1. Create extractor class implementing `TextExtractor`
2. Register in `extractors/__init__.py` → `get_extractor()`
3. Map MIME type to extractor class
4. System automatically uses new extractor

### Adding New Chunking Strategies

To add a new chunker:

1. Create chunker function in `chunkers/`
2. Update `indexer.py` to use new chunker
3. Add configuration options to Knowledge Source
4. System uses new chunking strategy

## Performance Characteristics

### Indexing Performance

- **Speed**: ~100-500 chunks/second (depends on chunk size)
- **Bottleneck**: Text extraction (PDF parsing is slowest)
- **Scalability**: Linear with number of inputs

### Search Performance

- **Latency**: <100ms for queries on 10K chunks
- **Scalability**: SQLite FTS5 handles up to ~1M chunks efficiently
- **Bottleneck**: SQLite file I/O (mitigated by WAL mode)

### Storage

- **Size**: ~1-2KB per chunk (SQLite overhead)
- **Compression**: SQLite uses compression internally
- **Backup**: Single file per source (easy to backup)

## Security Considerations

### File Access

- SQLite files stored as private Frappe Files
- Respects Frappe permissions
- Only accessible to users with Knowledge Source read permission

### Input Validation

- File type validation (MIME type checking)
- URL validation (prevents SSRF)
- Content hash deduplication (prevents duplicate processing)

### Agent Access Control

- Agents can only access linked Knowledge Sources
- Optional sources validated before tool execution
- Knowledge usage tracked in Agent Run (audit trail)

## Future Enhancements

### Phase 1.5: Semi-Semantic FTS

- Ingestion-time keyword tagging via LLM
- Query expansion
- Optional reranking with cross-encoder

### Phase 2: Vector Embeddings

- Add embedding generation
- Hybrid search (FTS + vectors)
- SQLite brute-force vectors or external vector DB

### Phase 3: Scalable Backends

- Chroma integration
- pgvector integration
- Cloud vector DBs (Pinecone, Weaviate)

### Phase 4: Advanced Features

- Multi-modal (images, tables)
- Knowledge graphs
- Automatic refresh/sync
- Per-source access control

## Comparison with Alternatives

### vs. Full RAG Framework (LangChain, LlamaIndex)

**Our Approach**:
- ✅ Control over architecture
- ✅ Frappe-native integration
- ✅ Lightweight (only what we need)
- ✅ Customizable to our needs

**Full Framework**:
- ❌ More dependencies
- ❌ Less control
- ❌ Harder to customize
- ❌ More complex

### vs. Direct Vector DB (Pinecone, Weaviate)

**Our Approach**:
- ✅ No external services (Phase 1)
- ✅ Portable (SQLite files)
- ✅ No API costs
- ✅ Works offline

**Direct Vector DB**:
- ❌ External dependency
- ❌ API costs
- ❌ Requires internet
- ❌ More complex setup

### vs. PostgreSQL Full-Text Search

**Our Approach**:
- ✅ Portable (single file)
- ✅ No database dependency
- ✅ Easy backup/restore
- ✅ Per-source isolation

**PostgreSQL**:
- ❌ Requires database server
- ❌ Shared resource
- ❌ More complex setup
- ❌ Harder to backup individual sources

## Conclusion

The Huf Knowledge System Phase 1 provides a solid foundation for knowledge management:

- **Portable**: SQLite files can be moved anywhere
- **Fast**: FTS5 provides sub-100ms search
- **Simple**: No external dependencies (Phase 1)
- **Extensible**: Easy to add new backends/extractors
- **Integrated**: Native Frappe integration

The architecture is designed for growth: Phase 1 establishes patterns that will scale to vector databases and advanced features in future phases.

---

**Questions?** See the testing guide or open an issue on GitHub.
