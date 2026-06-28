# RFC: Adapt Agno's Knowledge, VectorDB & Embedder Architecture for HUF

**Date**: 2026-03-03
**Status**: Proposal
**Authors**: Review Agent
**Related**: [Agno Framework](https://github.com/agno-agi/agno) (Apache 2.0 License)

---

## 1. Executive Summary

**Verdict: Yes — we should adapt Agno's vectordb, embedder, reader, and chunker code for HUF.**

Agno provides a clean, modular architecture with 18+ vector database backends, 18+ embedder providers, 20+ document readers, and 8 chunking strategies — all behind well-defined interfaces. The code is Apache 2.0 licensed (compatible with HUF), has fully optional dependencies per backend, and follows a consistent pattern that maps well to HUF's existing `KnowledgeBackend` abstraction.

HUF currently has SQLite FTS5 only (keyword/BM25 search, no semantic/vector search). This is the single largest gap versus modern AI agent frameworks. Adapting Agno's architecture would:

1. Add **semantic vector search** to HUF's knowledge system
2. Support **hybrid search** (BM25 + vector with Reciprocal Rank Fusion)
3. Enable **18+ vector DB backends** — users choose what fits their infra
4. Support **18+ embedding providers** — OpenAI, Cohere, local Ollama, etc.
5. Add **more document readers** — Excel, PowerPoint, improved PDF
6. Add **better chunking strategies** — recursive, semantic, markdown-aware, code-aware

**The approach is NOT to add Agno as a dependency.** Instead, we adapt their interfaces and selectively port implementations into HUF's codebase, integrating with Frappe's DocType system, permission model, and background job infrastructure.

---

## 2. What HUF Has Today

### Current Architecture
```
Knowledge Input (DocType)
    ↓
Extractors (PDF, DOCX, Text, HTML, URL)
    ↓
Chunker (LlamaIndex SentenceSplitter / fallback)
    ↓
SQLite FTS5 Backend (BM25 keyword search)
    ↓
Retriever (knowledge_search API)
    ↓
Context Builder (inject into agent prompt)
```

### Current Backend Interface (`huf/ai/knowledge/backends/__init__.py`)
```python
class KnowledgeBackend(ABC):
    def initialize(self, knowledge_source: str, config: Dict) -> None
    def add_chunks(self, chunks: List[Dict]) -> int
    def delete_chunks(self, input_id: str) -> int
    def search(self, query: str, top_k: int, filters: Optional[Dict]) -> List[ChunkResult]
    def clear(self) -> None
    def get_stats(self) -> Dict
```

### Current Limitations
| Area | Current State | Impact |
|------|--------------|--------|
| **Search type** | BM25 keyword only | Misses semantically related content |
| **Vector DBs** | 0 (SQLite FTS5 only) | No semantic search capability |
| **Embedders** | 0 | No vector generation |
| **Readers** | 5 (PDF, DOCX, Text, HTML, URL) | Missing Excel, PPT, Markdown-aware |
| **Chunking** | 1 (sentence-based) | No code-aware, semantic, or markdown chunking |
| **Hybrid search** | No | Can't combine keyword + semantic |
| **Metadata filters** | Reserved (not implemented) | Can't filter by document attributes |

### What's Working Well
- Clean `KnowledgeBackend` ABC with pluggable backends
- Commented-out `chroma` and `pgvector` entries in backend registry — the team anticipated this
- Frappe-integrated pipeline: Knowledge Source → Knowledge Input → chunks
- Background job processing with Redis locking
- Agent integration via Mandatory (auto-inject) and Optional (tool-based) modes
- Permission checks on knowledge access

---

## 3. What Agno Offers

### Agno's Architecture
```
Content Sources → Readers (20+) → Chunkers (8) → Embedders (18+) → VectorDB (18+) → Retrieval
```

### Key Interfaces (All Portable)

**VectorDb** — 153 LOC, pure ABC:
- `create()`, `insert()`, `upsert()`, `search()`, `delete()`, `drop()`, `exists()`
- Sync + async variants for every method
- Content hash deduplication built into interface
- Similarity threshold filtering

**Embedder** — ~25 LOC, dataclass ABC:
- `get_embedding(text) → List[float]`
- `dimensions`, `enable_batch`, `batch_size`
- Sync + async variants

**Document** — ~60 LOC, dataclass:
- `content`, `id`, `name`, `meta_data`, `embedding`, `reranking_score`
- `embed()` method for self-embedding
- Serialization helpers

**Reader** — ~100 LOC, dataclass ABC:
- `read(obj) → List[Document]`
- Built-in chunking support
- Content type detection

**ChunkingStrategy** — ~200 LOC, ABC:
- `chunk(document) → List[Document]`
- Deterministic chunk ID generation
- Text cleaning utilities

### Backend Implementations (LOC)
| Backend | Lines | Dependencies |
|---------|-------|-------------|
| PgVector | 1,548 | `sqlalchemy`, `pgvector` |
| ChromaDB | 1,374 | `chromadb` |
| Qdrant | 1,111 | `qdrant-client` |
| LanceDB | 1,013 | `lancedb`, `tantivy` |
| Pinecone | 730 | `pinecone` |
| Redis | 682 | `redis`, `redisvl` |
| MongoDB | 1,400 | `pymongo` |
| Weaviate | 1,009 | `weaviate-client` |
| Milvus | 1,216 | `pymilvus` |

**All dependencies are optional** — each backend's import is wrapped in try/except with a helpful `ImportError` message.

### License Compatibility
Agno is **Apache License 2.0** — fully compatible with adapting code into HUF. We can copy, modify, and redistribute with attribution.

---

## 4. Adaptation Strategy

### Principle: Adapt Interfaces, Not the Orchestration Layer

Agno's `Knowledge` class (3,500 LOC, 144KB) is tightly coupled to Agno's `db` package, remote content system, and agent protocol. We should **NOT** copy this.

Instead, we:
1. **Adapt the interfaces** (VectorDb, Embedder, Reader, ChunkingStrategy, Document) into HUF's existing architecture
2. **Port selected backend implementations** that make sense for Frappe users
3. **Wire them into HUF's existing DocType pipeline** (Knowledge Source → Knowledge Input → Agent)
4. **Keep HUF's existing `KnowledgeBackend` ABC** and evolve it to support both keyword and vector search

### What to Copy/Adapt vs. Rewrite

| Component | Action | Rationale |
|-----------|--------|-----------|
| `Document` dataclass | **Adapt** — use as internal data model within backends | HUF has `ChunkResult`; extend it |
| `Embedder` base class | **Copy** — minimal, no dependencies | Clean interface, no Agno coupling |
| `OpenAIEmbedder` | **Adapt** — use LiteLLM instead of direct OpenAI | HUF already uses LiteLLM for everything |
| `VectorDb` base class | **Reference** — inform HUF's `KnowledgeBackend` evolution | HUF's ABC is simpler and sufficient; extend it |
| PgVector implementation | **Adapt** — port core logic, use Frappe's DB connection | High value, MariaDB/PostgreSQL are common in Frappe |
| ChromaDB implementation | **Adapt** — port core logic | Zero-infra option for development |
| Qdrant implementation | **Adapt** — port core logic | Popular managed option |
| LanceDB implementation | **Adapt** — port core logic | Zero-infra, file-based, excellent for simple setups |
| Readers (PDF, DOCX, Excel, PPT) | **Adapt** — port, remove Agno-specific bits | HUF already has PDF/DOCX; add Excel/PPT |
| Chunking strategies | **Adapt** — port recursive, markdown, code chunkers | HUF only has sentence-based today |
| `Knowledge` orchestration | **Rewrite** — keep HUF's Frappe-based pipeline | Too coupled to Agno internals |
| Reranker system | **Adapt** — port interface + Cohere implementation | Nice-to-have for quality |
| Filter system | **Adapt** — port filter expressions | Enables metadata-based filtering |

---

## 5. Implementation Plan

### Phase 1: Foundation — Embedder + Vector Backend Interface (Week 1-2)

**Goal**: Establish the embedding and vector search layer that all backends will use.

#### 1.1 Add Embedder System
Create `huf/ai/knowledge/embedders/` module:

```
huf/ai/knowledge/embedders/
├── __init__.py        # Base Embedder ABC + get_embedder() factory
├── base.py            # Embedder ABC (adapted from Agno)
├── litellm.py         # LiteLLM-based embedder (uses HUF's existing LiteLLM infra)
└── openai.py          # Direct OpenAI embedder (for when LiteLLM isn't needed)
```

**Key design decision**: Use **LiteLLM for embeddings** as the primary embedder, not direct provider SDKs. HUF already depends on LiteLLM for LLM calls — LiteLLM also supports `litellm.embedding()` for 25+ embedding providers through the same interface. This means:
- No new provider SDKs needed
- Reuses HUF's existing `AI Provider` credential storage
- Single dependency for all embedding providers

```python
# huf/ai/knowledge/embedders/base.py (adapted from Agno)
class Embedder(ABC):
    dimensions: int = 1536

    @abstractmethod
    def get_embedding(self, text: str) -> List[float]: ...

    @abstractmethod
    def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]: ...

# huf/ai/knowledge/embedders/litellm.py
class LiteLLMEmbedder(Embedder):
    """Embedding via LiteLLM — supports 25+ providers through one interface."""
    def __init__(self, model: str = "text-embedding-3-small", api_key: str = None):
        self.model = model
        self.api_key = api_key

    def get_embedding(self, text: str) -> List[float]:
        import litellm
        response = litellm.embedding(model=self.model, input=[text], api_key=self.api_key)
        return response.data[0]["embedding"]
```

#### 1.2 Extend KnowledgeBackend Interface
Evolve HUF's existing `KnowledgeBackend` ABC to support vector search:

```python
# huf/ai/knowledge/backends/__init__.py (extended)
class KnowledgeBackend(ABC):
    # Existing methods (unchanged)
    def initialize(self, knowledge_source: str, config: Dict) -> None: ...
    def add_chunks(self, chunks: List[Dict]) -> int: ...
    def delete_chunks(self, input_id: str) -> int: ...
    def search(self, query: str, top_k: int, filters: Optional[Dict]) -> List[ChunkResult]: ...
    def clear(self) -> None: ...
    def get_stats(self) -> Dict: ...

    # NEW: Capabilities query
    def get_search_types(self) -> List[str]:
        """Return supported search types: 'keyword', 'vector', 'hybrid'."""
        return ["keyword"]

    def requires_embedder(self) -> bool:
        """Whether this backend needs an embedder for indexing/search."""
        return False
```

This is **backward compatible** — `SQLiteFTSBackend` continues working unchanged.

#### 1.3 Update Knowledge Source DocType
Add fields to support vector backends:

| New Field | Type | Purpose |
|-----------|------|---------|
| `knowledge_type` options | Extended Select | Add `qdrant`, `chroma`, `pgvector`, `lancedb` |
| `embedding_model` | Data | Embedding model name (e.g., `text-embedding-3-small`) |
| `embedding_provider` | Link to AI Provider | Which provider's API key to use for embeddings |
| `search_type` | Select | `keyword` / `vector` / `hybrid` |
| `vector_dimensions` | Int | Embedding dimensions (auto-detected or manual) |
| `similarity_threshold` | Float | Minimum similarity score (0.0–1.0) |
| `connection_config` | JSON | Backend-specific connection params (URL, API key, etc.) |

#### 1.4 Update Indexing Pipeline
Modify `indexer.py` to generate embeddings when backend requires them:

```python
# In process_knowledge_input():
backend = backend_class()
backend.initialize(source.name, config)

if backend.requires_embedder():
    embedder = get_embedder(source)  # from Knowledge Source config
    for chunk in chunk_data:
        chunk["embedding"] = embedder.get_embedding(chunk["text"])

backend.add_chunks(chunk_data)
```

#### 1.5 Update ChunkResult
Extend to carry embedding and similarity score:

```python
@dataclass
class ChunkResult:
    chunk_id: str
    text: str
    title: Optional[str] = None
    score: float = 0.0
    source: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    embedding: Optional[List[float]] = None  # NEW
    content_id: Optional[str] = None         # NEW: link to Knowledge Input
```

---

### Phase 2: First Vector Backends (Week 2-3)

**Goal**: Ship 2-3 vector backends that cover the most common deployment scenarios.

#### 2.1 Qdrant Backend (Recommended First)
**Why first**: Popular, good free tier (Qdrant Cloud), runs locally too, excellent hybrid search, well-documented Python client.

```
huf/ai/knowledge/backends/qdrant.py
```

Adapted from Agno's `vectordb/qdrant/qdrant.py` (1,111 lines). We'll port ~400-500 lines of core logic:
- Collection creation with vector + optional sparse (BM25) config
- Document insertion with embedding
- Vector search, keyword search, and hybrid search
- Delete by input_id
- Stats (collection info)

**Dependencies**: `qdrant-client` (optional extra in pyproject.toml)

#### 2.2 ChromaDB Backend (Zero-Infra Dev Option)
**Why**: Embedded database, no server needed, perfect for development and small deployments.

```
huf/ai/knowledge/backends/chroma.py
```

Adapted from Agno's `vectordb/chroma/chromadb.py` (1,374 lines). Core logic ~300-400 lines:
- Collection creation
- Persistent embedded mode (file-based, like SQLite)
- Hybrid search with Reciprocal Rank Fusion
- Metadata filtering

**Dependencies**: `chromadb` (optional extra)

#### 2.3 LanceDB Backend (File-Based, Zero-Server)
**Why**: File-based like SQLite, no server needed, fast, supports hybrid search with Tantivy.

```
huf/ai/knowledge/backends/lancedb.py
```

Adapted from Agno's `vectordb/lancedb/lance_db.py` (1,013 lines). Core logic ~300 lines:
- Table creation from PyArrow schema
- Vector + optional FTS with Tantivy
- File-based storage in `private/files/knowledge/`

**Dependencies**: `lancedb`, `tantivy` (optional extras)

#### 2.4 Update Backend Registry

```python
# huf/ai/knowledge/backends/__init__.py
backends = {
    "sqlite_fts": "huf.ai.knowledge.backends.sqlite_fts.SQLiteFTSBackend",
    "qdrant": "huf.ai.knowledge.backends.qdrant.QdrantBackend",
    "chroma": "huf.ai.knowledge.backends.chroma.ChromaBackend",
    "lancedb": "huf.ai.knowledge.backends.lancedb.LanceDBBackend",
}
```

---

### Phase 3: Enhanced Readers & Chunkers (Week 3-4)

#### 3.1 Additional Document Readers
Port from Agno's `knowledge/reader/` with Frappe adaptations:

```
huf/ai/knowledge/extractors/
├── __init__.py      # (existing) base + registry
├── pdf.py           # (existing) — enhance with Agno's page-aware extraction
├── docx.py          # (existing) — keep as-is
├── text.py          # (existing) — keep as-is
├── html.py          # (existing) — keep as-is
├── url.py           # (existing) — keep as-is
├── excel.py         # NEW: from Agno's ExcelReader (openpyxl)
├── pptx.py          # NEW: from Agno's PPTXReader (python-pptx)
└── markdown.py      # NEW: markdown-aware extraction preserving structure
```

**Excel** is high-value for Frappe/ERPNext users who often export data to Excel.
**PPTX** is useful for ingesting presentation content.

#### 3.2 Additional Chunking Strategies
Port from Agno's `knowledge/chunking/`:

```
huf/ai/knowledge/chunkers/
├── __init__.py      # Chunker ABC + factory
├── sentence.py      # (existing) — keep as-is
├── recursive.py     # NEW: Agno's RecursiveChunker — split by paragraph, then sentence
├── markdown.py      # NEW: respects heading hierarchy
├── code.py          # NEW: respects function/class boundaries
└── fixed.py         # NEW: simple fixed-size (useful baseline)
```

**Update Knowledge Source DocType** to add `chunking_strategy` field:
- Options: `sentence` (default), `recursive`, `markdown`, `code`, `fixed`

---

### Phase 4: Hybrid Search & Retrieval Improvements (Week 4-5)

#### 4.1 Hybrid Search in Retriever
Update `retriever.py` to support different search types:

```python
def knowledge_search(query, knowledge_source, top_k=5, filters=None, search_type=None):
    source = frappe.get_doc("Knowledge Source", source_name)

    # Use source's configured search type, or override
    effective_search_type = search_type or source.search_type or "keyword"

    backend = get_backend(source.knowledge_type)()
    backend.initialize(source.name, config)

    if effective_search_type == "hybrid" and "hybrid" in backend.get_search_types():
        # Backend handles hybrid internally (RRF fusion)
        results = backend.search(query, top_k, filters)
    elif effective_search_type == "vector" and backend.requires_embedder():
        # Pure vector search
        embedder = get_embedder(source)
        query_embedding = embedder.get_embedding(query)
        results = backend.vector_search(query_embedding, top_k, filters)
    else:
        # Keyword search (existing behavior)
        results = backend.search(query, top_k, filters)
```

#### 4.2 Metadata Filtering
Add metadata filter support (adapted from Agno's `filters.py`):

```python
# In knowledge_search():
results = backend.search(query, top_k, filters={
    "input_type": "File",
    "file_type": "application/pdf",
})
```

This enables agents to filter knowledge by document type, source, date, etc.

#### 4.3 Reranker Support (Optional)
Add optional reranking after retrieval:

```python
# huf/ai/knowledge/rerankers/
├── __init__.py    # Reranker ABC
├── cohere.py      # Cohere Rerank API
└── litellm.py     # LiteLLM-based reranking (if supported)
```

---

### Phase 5: DocType & Frontend Updates (Week 5-6)

#### 5.1 Knowledge Source DocType Updates
- Expand `knowledge_type` options
- Add embedding configuration fields
- Add search type selector
- Add connection configuration (collapsible section)
- Dynamic field visibility based on `knowledge_type`

#### 5.2 Knowledge Source Controller Updates
- Validate embedding config when vector backend selected
- Test connection on save (for Qdrant, etc.)
- Show estimated cost for embedding (token count × model pricing)

#### 5.3 Frontend Updates (Optional, Lower Priority)
- Show search type in Knowledge Source form
- Embedding model selector (linked to AI Provider models)
- Connection test button for remote vector DBs
- Visual indicator of backend type (keyword vs. vector vs. hybrid)

---

## 6. Dependency Management

### New Optional Dependencies (in pyproject.toml)

```toml
[project.optional-dependencies]
# Knowledge backends (all optional)
knowledge-qdrant = ["qdrant-client>=1.7.0"]
knowledge-chroma = ["chromadb>=0.4.0"]
knowledge-lancedb = ["lancedb>=0.26.0", "tantivy"]

# Document readers (optional)
knowledge-excel = ["openpyxl"]
knowledge-pptx = ["python-pptx"]

# Embeddings (LiteLLM already handles most, but for local)
knowledge-local-embeddings = ["sentence-transformers"]
```

### Import Pattern (from Agno)
Every backend uses try/except at import time:
```python
try:
    from qdrant_client import QdrantClient
except ImportError:
    raise ImportError(
        "`qdrant-client` not installed. Install it with: pip install qdrant-client"
    )
```

This ensures HUF works without any vector DB dependencies — they're only needed when configured.

---

## 7. Migration Path

### Existing SQLite FTS Users
**Zero breaking changes.** SQLite FTS5 remains the default. Existing Knowledge Sources continue working unchanged.

### Upgrading to Vector Search
1. Install the desired backend: `pip install qdrant-client`
2. Edit Knowledge Source → change `knowledge_type` to `qdrant`
3. Configure embedding model and connection
4. Click "Rebuild Index" — chunks are re-processed with embeddings
5. Agents automatically use the new backend for search

### Recommended Migration
- **Development**: Use ChromaDB or LanceDB (embedded, no server)
- **Production**: Use Qdrant Cloud (managed) or self-hosted Qdrant
- **Keep SQLite FTS5** for simple keyword-only use cases where semantic search isn't needed

---

## 8. Architecture Diagram (After Implementation)

```
Knowledge Input (DocType)
    ↓
Extractors (PDF, DOCX, Text, HTML, URL, Excel, PPTX)
    ↓
Chunkers (Sentence, Recursive, Markdown, Code, Fixed)
    ↓
┌──────────────────────┐
│ if vector backend:   │
│   Embedder           │
│   (LiteLLM/OpenAI/   │
│    Ollama/local)      │
└──────┬───────────────┘
       ↓
┌──────────────────────────────┐
│ Backend (user's choice)      │
│ ┌──────────┐ ┌─────────────┐ │
│ │SQLite    │ │Qdrant       │ │
│ │FTS5      │ │(vector+BM25)│ │
│ ├──────────┤ ├─────────────┤ │
│ │ChromaDB  │ │LanceDB      │ │
│ │(embedded)│ │(file-based) │ │
│ └──────────┘ └─────────────┘ │
└──────────────────────────────┘
       ↓
Retriever (keyword / vector / hybrid)
    ↓
[Optional Reranker]
    ↓
Context Builder → Agent Prompt
```

---

## 9. What We're NOT Doing (and Why)

| Agno Feature | Decision | Rationale |
|-------------|----------|-----------|
| Agno's `Knowledge` class | Skip | Too coupled to Agno's DB/remote layers; HUF has its own pipeline |
| Agno's `db` package (13 storage backends) | Skip | HUF uses Frappe's MariaDB/DocType system |
| Cloud storage loaders (S3, GCS, Azure) | Defer | Can be added later via `input_type` expansion |
| PgVector backend | Defer | Frappe typically uses MariaDB, not PostgreSQL; lower priority |
| All 18+ vector backends | Defer | Start with 3 (Qdrant, ChromaDB, LanceDB); add more on demand |
| Agno's `Agent` class | Skip | HUF has its own agent system |
| Memory/LearningMachine | Separate RFC | Important but separate from knowledge/RAG |
| MCP Server exposure | Separate RFC | Valuable but orthogonal |
| Adding Agno as pip dependency | No | We adapt code, not depend on framework |

---

## 10. Effort Estimate

| Phase | Scope | Estimated Effort |
|-------|-------|-----------------|
| Phase 1: Foundation | Embedder + interface evolution | ~500-700 LOC new code |
| Phase 2: Vector backends | 3 backends (Qdrant, Chroma, LanceDB) | ~1,200-1,500 LOC adapted |
| Phase 3: Readers & chunkers | Excel, PPTX readers + 3 chunkers | ~600-800 LOC adapted |
| Phase 4: Hybrid search | Retriever updates, metadata filters | ~300-400 LOC |
| Phase 5: DocType updates | Schema + controller + frontend | ~200 LOC + JSON changes |
| **Total** | | **~2,800-3,400 LOC** |

For comparison, the code we're adapting from Agno is ~20,000 LOC across all backends. We're taking ~15-17% of it — the most valuable parts.

---

## 11. Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| LiteLLM embedding API changes | Low | Pin LiteLLM version; fallback to direct OpenAI SDK |
| Vector DB client API changes | Medium | Pin dependency versions; each backend is isolated |
| Performance with large knowledge bases | Medium | Start with benchmarks; LanceDB handles 1M+ vectors |
| Embedding costs for large corpora | Medium | Show estimated cost before rebuild; support local embedders |
| Breaking existing SQLite FTS setups | Very Low | SQLite FTS is unchanged; zero migration needed |

---

## 12. Success Criteria

1. **Existing tests pass** — SQLite FTS5 continues working identically
2. **A user can create a Qdrant-backed Knowledge Source** from the Frappe Desk form, add documents, and search semantically
3. **Hybrid search** returns better results than keyword-only for semantic queries
4. **Zero mandatory new dependencies** — all vector backends are optional extras
5. **Knowledge Source DocType** has a clean UI for choosing backend + embedding config
6. **Agent integration** works transparently — agents use whatever backend the Knowledge Source is configured with

---

## 13. Files to be Created/Modified

### New Files
```
huf/ai/knowledge/embedders/__init__.py
huf/ai/knowledge/embedders/base.py
huf/ai/knowledge/embedders/litellm.py
huf/ai/knowledge/backends/qdrant.py
huf/ai/knowledge/backends/chroma.py
huf/ai/knowledge/backends/lancedb.py
huf/ai/knowledge/chunkers/__init__.py
huf/ai/knowledge/chunkers/recursive.py
huf/ai/knowledge/chunkers/markdown.py
huf/ai/knowledge/chunkers/code.py
huf/ai/knowledge/chunkers/fixed.py
huf/ai/knowledge/extractors/excel.py
huf/ai/knowledge/extractors/pptx.py
huf/ai/knowledge/rerankers/__init__.py (Phase 4)
```

### Modified Files
```
huf/ai/knowledge/backends/__init__.py          # Extend KnowledgeBackend ABC + registry
huf/ai/knowledge/indexer.py                     # Add embedding step
huf/ai/knowledge/retriever.py                   # Support vector/hybrid search
huf/ai/knowledge/context_builder.py             # Minor: pass search_type
huf/huf/doctype/knowledge_source/knowledge_source.json  # New fields
huf/huf/doctype/knowledge_source/knowledge_source.py    # Validation for new fields
pyproject.toml                                   # Optional dependencies
```

---

## Appendix A: Agno Code Reference

The following Agno source files were analyzed for this RFC:

| File | Lines | Adaptation |
|------|-------|-----------|
| `agno/vectordb/base.py` | 153 | Reference for interface design |
| `agno/vectordb/qdrant/qdrant.py` | 1,111 | Port ~400 LOC core logic |
| `agno/vectordb/chroma/chromadb.py` | 1,374 | Port ~350 LOC core logic |
| `agno/vectordb/lancedb/lance_db.py` | 1,013 | Port ~300 LOC core logic |
| `agno/knowledge/embedder/base.py` | ~25 | Copy interface |
| `agno/knowledge/embedder/openai.py` | ~120 | Reference (use LiteLLM instead) |
| `agno/knowledge/reader/pdf_reader.py` | ~200 | Reference for PDF improvements |
| `agno/knowledge/chunking/recursive.py` | ~150 | Port chunking logic |
| `agno/knowledge/chunking/strategy.py` | ~200 | Reference for chunker ABC |
| `agno/knowledge/document/base.py` | ~60 | Reference for Document model |
| `agno/vectordb/distance.py` | 7 | Copy enums |
| `agno/vectordb/search.py` | 7 | Copy enums |
| `agno/vectordb/score.py` | 106 | Copy score normalization |
| `agno/filters.py` | ~400 | Reference for metadata filtering |

**License**: Apache 2.0 (Agno Inc., 2025-2026) — permits modification and redistribution with attribution.

---

## Appendix B: LiteLLM Embedding Support

LiteLLM's `litellm.embedding()` already supports:
- OpenAI (`text-embedding-3-small`, `text-embedding-3-large`, `text-embedding-ada-002`)
- Azure OpenAI (all embedding models)
- Cohere (`embed-english-v3.0`, `embed-multilingual-v3.0`)
- AWS Bedrock (Titan Embeddings, Cohere on Bedrock)
- Google VertexAI (textembedding-gecko)
- HuggingFace (Inference API)
- Ollama (local embedding models like `nomic-embed-text`)
- Voyage AI, Mistral, and others

This means HUF gets **25+ embedding providers** through the same LiteLLM dependency it already uses for LLM calls.
