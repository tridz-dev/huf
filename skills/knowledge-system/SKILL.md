---
name: knowledge-system
description: Portable RAG (Retrieval-Augmented Generation) system using SQLite FTS5 for knowledge management, ingestion, and retrieval in HUF agents.
category: features
---

# Knowledge System (RAG)

The Knowledge System provides a portable, low-ops RAG implementation for HUF agents. It uses SQLite FTS5 for keyword-based search with BM25 ranking, enabling agents to access domain-specific knowledge without external vector databases.

## Overview

The Knowledge System allows you to:

- Create **Knowledge Sources** - Portable containers for indexed knowledge
- Add **Knowledge Inputs** - Files, text snippets, or URLs to be indexed
- Automatically chunk and index content using SQLite FTS5
- Provide **Mandatory** (auto-injected) or **Optional** (tool-based) knowledge to agents
- Search across knowledge sources using BM25 ranking

## Key Files

| File | Purpose |
|------|---------|
| `huf/huf/doctype/knowledge_source/knowledge_source.py` | Knowledge Source DocType - container for indexed knowledge |
| `huf/huf/doctype/knowledge_input/knowledge_input.py` | Knowledge Input DocType - individual content items |
| `huf/huf/doctype/agent_knowledge/agent_knowledge.py` | Agent Knowledge child table - links agents to sources |
| `huf/ai/knowledge/indexer.py` | Ingestion pipeline - background processing with Redis locks |
| `huf/ai/knowledge/backends/sqlite_fts.py` | SQLite FTS5 backend - storage and search |
| `huf/ai/knowledge/backends/__init__.py` | Backend abstraction layer |
| `huf/ai/knowledge/retriever.py` | Search and retrieval with multi-source aggregation |
| `huf/ai/knowledge/context_builder.py` | Context assembly for agent prompts |
| `huf/ai/knowledge/tool.py` | Agent tools: `knowledge_search`, `get_knowledge_sources` |
| `huf/ai/knowledge/chunkers/sentence.py` | Sentence-aware text chunking via LlamaIndex |
| `huf/ai/knowledge/extractors/` | Text extractors for PDF, DOCX, HTML, URL, Text |
| `frontend/src/types/knowledge.types.ts` | TypeScript type definitions |
| `frontend/src/components/knowledge/` | React components for knowledge management UI |

## How It Works

### Ingestion Pipeline Flow

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Knowledge Input │────▶│ Text Extraction  │────▶│  Chunking       │
│  (File/Text/URL)│     │ (PDF/DOCX/HTML)  │     │ (512 chars)     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                          │
                                                          ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Status: Ready │◀────│  SQLite FTS5     │◀────│  BM25 Index     │
│                 │     │  (FTS5 Virtual)  │     │  (Tokenize)     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

1. **Input Creation**: User creates a Knowledge Input (File, Text, or URL)
2. **Queue Processing**: `after_insert` triggers `process_knowledge_input()` as background job
3. **Acquire Lock**: Redis lock (`knowledge_index_{source}`) ensures single-writer access
4. **Text Extraction**: Based on input type:
   - **File**: PDF (`pypdf`/`PyPDF2`), DOCX (`python-docx`), HTML, Text
   - **Text**: Direct content
   - **URL**: Fetched via `requests` + `BeautifulSoup`
5. **Chunking**: LlamaIndex `SentenceSplitter` (default: 512 chars, 50 overlap)
6. **Indexing**: Chunks stored in SQLite with FTS5 virtual table for full-text search
7. **Status Update**: Input marked as `Indexed`, source stats updated

### Agent Knowledge Binding

Agents link to knowledge sources via the **Agent Knowledge** child table:

| Field | Description |
|-------|-------------|
| `knowledge_source` | Link to Knowledge Source |
| `mode` | `Mandatory` (auto-injected) or `Optional` (tool-based) |
| `priority` | Retrieval priority (higher = first) |
| `max_chunks` | Max chunks to retrieve (default: 5) |
| `token_budget` | Max tokens to inject (default: 2000) |

### Mandatory Knowledge Mode

When `mode="Mandatory"`:

1. Before agent execution, `build_knowledge_context()` is called
2. Searches all mandatory sources using the user's query
3. Injects context into system prompt:
   ```markdown
   ## Relevant Knowledge
   ### Source Title
   [Chunk Text]
   ...
   ---
   [User Prompt]
   ```
4. Best for: Rules, guidelines, persona definitions that must always be present

### Optional Knowledge Mode

When `mode="Optional"`:

1. Agent receives `knowledge_search` and `get_knowledge_sources` tools
2. Agent can query knowledge on-demand during conversation
3. Best for: Large reference docs, knowledge bases that shouldn't clutter every prompt

### Storage Backend

**SQLite FTS5 Backend** (`sqlite_fts`):

- **Location**: `/private/files/knowledge/{source_name}.sqlite3`
- **Schema**:
  - `chunks` table: Stores chunk_id, input_id, text, metadata
  - `chunks_fts` virtual table: FTS5 index with `porter unicode61` tokenization
  - Triggers: Auto-sync between `chunks` and `chunks_fts` on INSERT/UPDATE/DELETE
- **Ranking**: BM25 with configurable weights
- **Pragmas**: WAL mode, memory-mapped I/O for performance

## Extension Points

### Adding a New Extractor

1. Create extractor class in `huf/ai/knowledge/extractors/`:

```python
from huf.ai.knowledge.extractors import TextExtractor, ExtractedText

class CSVExtractor(TextExtractor):
    def extract(self, file_path: str) -> ExtractedText:
        # Extract text from CSV
        return ExtractedText(
            text=extracted_text,
            title="CSV Data",
            metadata={"file_type": "csv", "rows": row_count}
        )
```

2. Register in `huf/ai/knowledge/extractors/__init__.py`:

```python
extractors = {
    "text/csv": "huf.ai.knowledge.extractors.csv.CSVExtractor",
    # ...
}
```

### Adding a New Backend

1. Create backend class inheriting from `KnowledgeBackend`:

```python
from huf.ai.knowledge.backends import KnowledgeBackend, ChunkResult

class MyBackend(KnowledgeBackend):
    def initialize(self, knowledge_source: str, config: dict) -> None:
        # Initialize connection/storage
        pass
    
    def add_chunks(self, chunks: list) -> int:
        # Add chunks to index
        pass
    
    def search(self, query: str, top_k: int = 5, filters=None) -> list[ChunkResult]:
        # Return ranked results
        pass
    
    def clear(self) -> None:
        # Clear all chunks
        pass
    
    def get_stats(self) -> dict:
        # Return statistics
        pass
```

2. Register in `huf/ai/knowledge/backends/__init__.py`:

```python
backends = {
    "my_backend": "huf.ai.knowledge.backends.my_backend.MyBackend",
    # ...
}
```

### Custom Chunking Strategy

Replace the chunker in `huf/ai/knowledge/chunkers/sentence.py`:

```python
def chunk_text(text: str, chunk_size: int = 512, chunk_overlap: int = 50) -> list[Chunk]:
    # Your custom chunking logic
    return chunks
```

## Dependencies

### Required

- `llama-index-core` - Sentence-aware text chunking
- `sqlite3` - Built-in Python SQLite (FTS5 enabled)

### Optional (for extractors)

- `pypdf` or `PyPDF2` - PDF text extraction
- `python-docx` - DOCX text extraction
- `beautifulsoup4` - HTML/URL content extraction
- `requests` - URL fetching

### Vector Search (Optional)

- `pysqlite3-binary` - For `sqlite_vec` backend with vector search
- Embedding models configured per Knowledge Source

## Gotchas

### SQLite FTS5 Query Escaping

The FTS5 backend escapes special characters in queries to prevent syntax errors:
- Characters removed: `"`, `'`, `(`, `)`, `*`, `:`, `^`, `-`, `+`
- Multiple terms are joined with `OR`
- This may affect exact phrase matching

**Location**: `huf/ai/knowledge/backends/sqlite_fts.py:_escape_fts_query()`

### Redis Lock Timeout

Indexing operations use Redis locks with timeouts:
- **Processing**: 300 seconds (5 minutes)
- **Rebuilding**: 600 seconds (10 minutes)

Long-running operations may lose the lock. For large knowledge bases, consider batching inputs.

### File Storage Path

SQLite files are stored as private Frappe Files:
- **Path**: `sites/{site}/private/files/knowledge/{source}.sqlite3`
- Automatically registered in Frappe File doctype
- Deleted when Knowledge Source is deleted (`on_trash`)

### Chunk Size Validation

Knowledge Source validates chunk settings:
- Minimum chunk size: 100 characters
- Overlap must be less than chunk size
- Defaults: 512 chars size, 50 chars overlap

### Permission Handling

- **Agent execution**: Uses `ignore_permissions=True` for knowledge search (agent has explicit linkage)
- **Direct API calls**: Respects Frappe permissions on Knowledge Source DocType
- **Diagnostics**: `get_search_diagnostics()` helps debug why sources are skipped

### Background Job Deduplication

Processing uses `deduplicate=True` to prevent duplicate jobs:
- Job ID: `process_input_{input_name}`
- Rebuild Job ID: `rebuild_index_{source_name}`

If a job is already running, new requests are ignored.

### Source Hash Deduplication

Knowledge Inputs compute SHA-256 hash for deduplication:
- File: Hash of file URL (not content)
- Text: Hash of text content
- URL: Hash of URL

Duplicate detection runs during `validate()`, before insert.

### Token Budget Estimation

Context builder uses rough estimation (4 chars = 1 token):
```python
chunk_tokens = len(chunk["text"]) // 4
```

This is approximate - actual token count depends on the model's tokenizer.

### Multi-Source Search Aggregation

When searching multiple sources:
1. Each source returns up to `top_k` results
2. Results are merged and sorted by score
3. Final list limited to `top_k` total

This means individual source contributions may be reduced when searching many sources.
