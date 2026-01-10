# Huf Knowledge System — Phase 1 Implementation Plan

> **Branch**: `feature/knowledge-system-phase1`
> **Goal**: Deliver a stable, low-ops, portable knowledge system using SQLite Full-Text Search

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Principles](#2-architecture-principles)
3. [DocTypes Specification](#3-doctypes-specification)
4. [Child Tables Specification](#4-child-tables-specification)
5. [SQLite FTS Artifact Design](#5-sqlite-fts-artifact-design)
6. [LlamaIndex Integration Layer](#6-llamaindex-integration-layer)
7. [Core Python Modules](#7-core-python-modules)
8. [Ingestion Pipeline](#8-ingestion-pipeline)
9. [Retrieval System](#9-retrieval-system)
10. [Agent Integration](#10-agent-integration)
11. [Hooks & Events](#11-hooks--events)
12. [API Endpoints](#12-api-endpoints)
13. [Background Jobs](#13-background-jobs)
14. [Observability & Logging](#14-observability--logging)
15. [Frontend Components](#15-frontend-components)
16. [Provider Extensibility](#16-provider-extensibility)
17. [Testing Strategy](#17-testing-strategy)
18. [Migration & Rollout](#18-migration--rollout)
19. [Future Phases](#19-future-phases)

---

## 1. Executive Summary

### 1.1 What We're Building

A first-class knowledge system for Huf that:
- Allows agents to access curated knowledge sources
- Uses SQLite FTS for fast, portable keyword search (Phase 1)
- Positions LlamaIndex as integration layer, not architecture owner
- Follows the same abstraction pattern as LiteLLM for providers

### 1.2 Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| SQLite FTS only (Phase 1) | No embeddings, no native extensions, maximum portability |
| Frappe DB = source of truth | Files, metadata, permissions in MariaDB |
| SQLite = search artifact | Derived, rebuildable, portable |
| LlamaIndex as adapter | Backend pluggability without architecture lock-in |
| Mandatory + Optional modes | Autoload vs tool-based knowledge access |

### 1.3 Phase 1 Scope

**Included:**
- Keyword search via SQLite FTS5
- BM25 ranking
- Multiple knowledge sources per agent
- Mandatory (autoload) and Optional (tool) knowledge
- File upload + pasted text ingestion
- Safe parallel reads

**Not Included:**
- Embeddings / Vector similarity
- ANN (Approximate Nearest Neighbor)
- External vector databases

---

## 2. Architecture Principles

### 2.1 Separation of Concerns

```
┌─────────────────────────────────────────────────────────────────┐
│                         Agent Layer                              │
│  (Agents bind to Knowledge Sources, not databases or files)     │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Knowledge Abstraction Layer                   │
│  (knowledge_search contract, mandatory/optional modes)           │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                   LlamaIndex Integration Layer                   │
│  (Retrieval abstraction, backend adapters)                       │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Storage Backends                            │
│  Phase 1: SQLite FTS | Future: Chroma, pgvector, Cloud VDBs     │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
                    ┌──────────────────┐
                    │   File Upload    │
                    │   Text Paste     │
                    └────────┬─────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────────┐
│                     Knowledge Input                             │
│  (Tracks raw content, status, source_hash)                      │
└────────────────────────┬───────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────┐
│                  Ingestion Pipeline (Background Job)            │
│  1. Extract text  2. Chunk  3. Insert SQLite  4. Update FTS     │
└────────────────────────┬───────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────┐
│                   Knowledge Source                              │
│  (SQLite FTS artifact, chunk_size config, status)               │
└────────────────────────┬───────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────┐
│                     Agent Knowledge                             │
│  (mode: Mandatory/Optional, priority, token_budget)             │
└────────────────────────┬───────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────┐
│                        Agent Run                                │
│  (knowledge_sources_used, chunks_injected)                      │
└────────────────────────────────────────────────────────────────┘
```

### 2.3 Core Invariants

1. **Agent runs are read-only** — Indexing happens only in background jobs
2. **One retrieval contract** — Agents access knowledge only via `knowledge_search`
3. **Single writer per Knowledge Source** — Redis lock during ingestion
4. **SQLite files are artifacts** — Can be rebuilt from Frappe inputs at any time

---

## 3. DocTypes Specification

### 3.1 Knowledge Source

> Portable, indexed knowledge container

**File**: `huf/huf/doctype/knowledge_source/knowledge_source.json`

**Naming Rule**: `field:source_name`

| Fieldname | Fieldtype | Label | Required | Options/Default | Description |
|-----------|-----------|-------|----------|-----------------|-------------|
| `source_name` | Data | Source Name | ✓ | unique | Unique identifier for the knowledge source |
| `description` | Small Text | Description | | | Human-readable description of the knowledge source |
| `knowledge_type` | Select | Knowledge Type | ✓ | `sqlite_fts` | Backend type (Phase 1 only supports sqlite_fts) |
| `scope` | Select | Scope | ✓ | `Site\nWorkspace\nAgent\nGlobal` | Access scope for the knowledge source |
| `storage_mode` | Select | Storage Mode | ✓ | `Frappe File` (default) | How source files are stored |
| `sqlite_file` | Attach | SQLite File | | | Private Frappe File reference to SQLite artifact |
| `sqlite_file_path` | Data | SQLite File Path | | read_only | Actual file path for internal use |
| `chunk_size` | Int | Chunk Size | | `512` | Number of characters per chunk |
| `chunk_overlap` | Int | Chunk Overlap | | `50` | Overlap between consecutive chunks |
| `status` | Select | Status | | `Pending\nIndexing\nReady\nError\nRebuilding` | Current state of the knowledge source |
| `last_indexed_at` | Datetime | Last Indexed At | | read_only | Timestamp of last successful indexing |
| `total_chunks` | Int | Total Chunks | | read_only | Number of chunks in the index |
| `total_inputs` | Int | Total Inputs | | read_only | Number of input documents |
| `index_size_bytes` | Int | Index Size (bytes) | | read_only | Size of SQLite artifact |
| `error_message` | Small Text | Error Message | | read_only | Last error message if status is Error |
| `disabled` | Check | Disabled | | `0` | Whether the knowledge source is disabled |

**Sections:**
- **Configuration** (Section Break): `source_name`, `description`, `knowledge_type`, `scope`
- **Storage Settings** (Section Break): `storage_mode`, `sqlite_file`, `sqlite_file_path`
- **Chunking Settings** (Section Break): `chunk_size`, `chunk_overlap`
- **Status** (Section Break): `status`, `last_indexed_at`, `total_chunks`, `total_inputs`, `index_size_bytes`, `error_message`

**Actions:**
- **Rebuild Index**: Clear and rebuild SQLite artifact from all inputs
- **Test Search**: Open modal to test search queries against this source

**Python Controller**: `huf/huf/doctype/knowledge_source/knowledge_source.py`

```python
# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _


class KnowledgeSource(Document):
    def validate(self):
        self.validate_chunk_settings()
        
    def validate_chunk_settings(self):
        if self.chunk_size and self.chunk_size < 100:
            frappe.throw(_("Chunk size must be at least 100 characters"))
        if self.chunk_overlap and self.chunk_overlap >= self.chunk_size:
            frappe.throw(_("Chunk overlap must be less than chunk size"))
    
    def before_save(self):
        if not self.chunk_size:
            self.chunk_size = 512
        if not self.chunk_overlap:
            self.chunk_overlap = 50
        if not self.status:
            self.status = "Pending"
    
    def on_trash(self):
        # Delete SQLite artifact file
        if self.sqlite_file:
            frappe.delete_doc("File", {"file_url": self.sqlite_file}, force=True)
        
        # Delete all related inputs
        frappe.db.delete("Knowledge Input", {"knowledge_source": self.name})


@frappe.whitelist()
def rebuild_index(knowledge_source: str):
    """Trigger a full index rebuild for the knowledge source."""
    from huf.ai.knowledge.indexer import rebuild_knowledge_index
    
    doc = frappe.get_doc("Knowledge Source", knowledge_source)
    doc.status = "Rebuilding"
    doc.save()
    
    frappe.enqueue(
        rebuild_knowledge_index,
        queue="long",
        knowledge_source=knowledge_source,
        job_id=f"rebuild_index_{knowledge_source}"
    )
    
    return {"status": "queued", "message": _("Index rebuild has been queued")}


@frappe.whitelist()
def test_search(knowledge_source: str, query: str, top_k: int = 5):
    """Test search against a knowledge source."""
    from huf.ai.knowledge.retriever import knowledge_search
    
    results = knowledge_search(
        query=query,
        knowledge_source=knowledge_source,
        top_k=int(top_k)
    )
    
    return results
```

**Client Script**: `huf/huf/doctype/knowledge_source/knowledge_source.js`

```javascript
// Copyright (c) 2025, Huf and contributors
// For license information, please see license.txt

frappe.ui.form.on("Knowledge Source", {
    refresh(frm) {
        // Add Rebuild Index button
        if (!frm.is_new() && frm.doc.status !== "Indexing" && frm.doc.status !== "Rebuilding") {
            frm.add_custom_button(__("Rebuild Index"), function() {
                frappe.confirm(
                    __("This will clear the existing index and rebuild it from all inputs. Continue?"),
                    function() {
                        frappe.call({
                            method: "huf.huf.doctype.knowledge_source.knowledge_source.rebuild_index",
                            args: { knowledge_source: frm.doc.name },
                            callback: function(r) {
                                if (r.message) {
                                    frappe.show_alert({
                                        message: r.message.message,
                                        indicator: "green"
                                    });
                                    frm.reload_doc();
                                }
                            }
                        });
                    }
                );
            }, __("Actions"));
        }
        
        // Add Test Search button
        if (!frm.is_new() && frm.doc.status === "Ready") {
            frm.add_custom_button(__("Test Search"), function() {
                show_test_search_dialog(frm);
            }, __("Actions"));
        }
        
        // Status indicator
        if (frm.doc.status === "Ready") {
            frm.dashboard.set_headline_alert(
                __("Index ready with {0} chunks", [frm.doc.total_chunks]),
                "green"
            );
        } else if (frm.doc.status === "Error") {
            frm.dashboard.set_headline_alert(
                __("Error: {0}", [frm.doc.error_message]),
                "red"
            );
        } else if (frm.doc.status === "Indexing" || frm.doc.status === "Rebuilding") {
            frm.dashboard.set_headline_alert(__("Indexing in progress..."), "blue");
        }
    },
    
    knowledge_type(frm) {
        // Phase 1: Only sqlite_fts is supported
        if (frm.doc.knowledge_type && frm.doc.knowledge_type !== "sqlite_fts") {
            frappe.msgprint(__("Only SQLite FTS is supported in Phase 1"));
            frm.set_value("knowledge_type", "sqlite_fts");
        }
    }
});

function show_test_search_dialog(frm) {
    let d = new frappe.ui.Dialog({
        title: __("Test Search"),
        fields: [
            {
                label: __("Search Query"),
                fieldname: "query",
                fieldtype: "Small Text",
                reqd: 1
            },
            {
                label: __("Top K Results"),
                fieldname: "top_k",
                fieldtype: "Int",
                default: 5
            },
            {
                label: __("Results"),
                fieldname: "results_html",
                fieldtype: "HTML"
            }
        ],
        primary_action_label: __("Search"),
        primary_action(values) {
            frappe.call({
                method: "huf.huf.doctype.knowledge_source.knowledge_source.test_search",
                args: {
                    knowledge_source: frm.doc.name,
                    query: values.query,
                    top_k: values.top_k || 5
                },
                callback: function(r) {
                    if (r.message) {
                        let html = render_search_results(r.message);
                        d.fields_dict.results_html.$wrapper.html(html);
                    }
                }
            });
        }
    });
    d.show();
}

function render_search_results(results) {
    if (!results || results.length === 0) {
        return `<p class="text-muted">${__("No results found")}</p>`;
    }
    
    let html = '<div class="search-results">';
    results.forEach((r, i) => {
        html += `
            <div class="result-item mb-3 p-3 border rounded">
                <div class="d-flex justify-content-between mb-2">
                    <strong>${r.title || 'Chunk ' + (i + 1)}</strong>
                    <span class="text-muted">Score: ${r.score?.toFixed(3) || 'N/A'}</span>
                </div>
                <p class="mb-0 small">${frappe.utils.escape_html(r.text?.substring(0, 300))}...</p>
            </div>
        `;
    });
    html += '</div>';
    return html;
}
```

---

### 3.2 Knowledge Input

> Tracks content ingested into a Knowledge Source

**File**: `huf/huf/doctype/knowledge_input/knowledge_input.json`

**Naming Rule**: `autoname: hash`

| Fieldname | Fieldtype | Label | Required | Options/Default | Description |
|-----------|-----------|-------|----------|-----------------|-------------|
| `knowledge_source` | Link | Knowledge Source | ✓ | options: Knowledge Source | Parent knowledge source |
| `input_type` | Select | Input Type | ✓ | `File\nText\nURL` | Type of input |
| `file` | Attach | File | | depends_on: input_type='File' | Uploaded file reference |
| `file_name` | Data | File Name | | read_only | Original file name |
| `file_type` | Data | File Type | | read_only | MIME type of the file |
| `text` | Long Text | Text | | depends_on: input_type='Text' | Pasted text content |
| `url` | Data | URL | | depends_on: input_type='URL' | URL to fetch content from |
| `source_hash` | Data | Source Hash | | read_only, unique | SHA-256 hash of source content for deduplication |
| `status` | Select | Status | | `Pending\nProcessing\nIndexed\nError` | Processing status |
| `error_message` | Small Text | Error Message | | read_only | Error details if failed |
| `chunks_created` | Int | Chunks Created | | read_only | Number of chunks generated |
| `processed_at` | Datetime | Processed At | | read_only | Timestamp of processing |
| `character_count` | Int | Character Count | | read_only | Total characters in extracted text |

**Python Controller**: `huf/huf/doctype/knowledge_input/knowledge_input.py`

```python
# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

import hashlib
import frappe
from frappe.model.document import Document
from frappe import _


class KnowledgeInput(Document):
    def validate(self):
        self.validate_input()
        self.compute_source_hash()
        self.check_duplicate()
    
    def validate_input(self):
        if self.input_type == "File" and not self.file:
            frappe.throw(_("File is required for File input type"))
        elif self.input_type == "Text" and not self.text:
            frappe.throw(_("Text content is required for Text input type"))
        elif self.input_type == "URL" and not self.url:
            frappe.throw(_("URL is required for URL input type"))
    
    def compute_source_hash(self):
        """Compute SHA-256 hash for deduplication."""
        content = ""
        if self.input_type == "File" and self.file:
            # Hash the file URL as we can't read content during validate
            content = self.file
        elif self.input_type == "Text":
            content = self.text or ""
        elif self.input_type == "URL":
            content = self.url or ""
        
        if content:
            self.source_hash = hashlib.sha256(content.encode()).hexdigest()
    
    def check_duplicate(self):
        """Check if this content already exists in the knowledge source."""
        if self.source_hash and not self.is_new():
            return
            
        if self.source_hash:
            existing = frappe.db.exists("Knowledge Input", {
                "knowledge_source": self.knowledge_source,
                "source_hash": self.source_hash,
                "name": ("!=", self.name or "")
            })
            if existing:
                frappe.throw(_("This content already exists in the knowledge source"))
    
    def before_save(self):
        if not self.status:
            self.status = "Pending"
        
        # Extract file metadata
        if self.input_type == "File" and self.file:
            file_doc = frappe.get_doc("File", {"file_url": self.file})
            self.file_name = file_doc.file_name
            self.file_type = file_doc.file_type or self.get_file_type_from_name(file_doc.file_name)
    
    def get_file_type_from_name(self, filename):
        """Infer file type from extension."""
        ext_map = {
            ".pdf": "application/pdf",
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
            ".html": "text/html",
            ".htm": "text/html",
            ".json": "application/json",
            ".csv": "text/csv",
        }
        import os
        _, ext = os.path.splitext(filename.lower())
        return ext_map.get(ext, "application/octet-stream")
    
    def after_insert(self):
        """Queue processing after insert."""
        self.queue_processing()
    
    def queue_processing(self):
        """Queue the input for processing."""
        from huf.ai.knowledge.indexer import process_knowledge_input
        
        frappe.enqueue(
            process_knowledge_input,
            queue="default",
            knowledge_input=self.name,
            job_id=f"process_input_{self.name}"
        )


@frappe.whitelist()
def reprocess_input(knowledge_input: str):
    """Reprocess a failed or pending input."""
    doc = frappe.get_doc("Knowledge Input", knowledge_input)
    doc.status = "Pending"
    doc.error_message = None
    doc.save()
    doc.queue_processing()
    
    return {"status": "queued", "message": _("Input has been queued for reprocessing")}
```

---

### 3.3 Agent Knowledge (Child Table)

> Maps agents to knowledge sources with configuration

**File**: `huf/huf/doctype/agent_knowledge/agent_knowledge.json`

**istable**: true

| Fieldname | Fieldtype | Label | Required | Options/Default | Description |
|-----------|-----------|-------|----------|-----------------|-------------|
| `knowledge_source` | Link | Knowledge Source | ✓ | options: Knowledge Source | Reference to knowledge source |
| `mode` | Select | Mode | ✓ | `Mandatory\nOptional` | How knowledge is accessed |
| `priority` | Int | Priority | | `0` | Retrieval priority (higher = first) |
| `max_chunks` | Int | Max Chunks | | `5` | Maximum chunks to retrieve per query |
| `token_budget` | Int | Token Budget | | `2000` | Max tokens to inject from this source |
| `description` | Small Text | Description | | | Override description for context |

**Python Controller**: `huf/huf/doctype/agent_knowledge/agent_knowledge.py`

```python
# Copyright (c) 2025, Huf and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class AgentKnowledge(Document):
    pass
```

---

## 4. Child Tables Specification

### 4.1 Knowledge Chunk (Internal, not exposed as DocType)

> Stored in SQLite FTS artifact, not in Frappe DB

**SQLite Schema:**

```sql
-- Main chunks table
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    input_id TEXT NOT NULL,
    input_type TEXT NOT NULL,
    source_title TEXT,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    char_start INTEGER,
    char_end INTEGER,
    metadata TEXT,  -- JSON blob for extensibility
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- FTS5 virtual table for full-text search
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text,
    source_title,
    content='chunks',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text, source_title) 
    VALUES (new.rowid, new.text, new.source_title);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text, source_title) 
    VALUES ('delete', old.rowid, old.text, old.source_title);
END;

CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text, source_title) 
    VALUES ('delete', old.rowid, old.text, old.source_title);
    INSERT INTO chunks_fts(rowid, text, source_title) 
    VALUES (new.rowid, new.text, new.source_title);
END;

-- Index for fast input_id lookups (for deletion)
CREATE INDEX IF NOT EXISTS idx_chunks_input_id ON chunks(input_id);
```

---

## 5. SQLite FTS Artifact Design

### 5.1 File Structure

```
/private/files/knowledge/
├── {knowledge_source_name}.sqlite3
├── {knowledge_source_name}.sqlite3-wal  (during writes)
└── {knowledge_source_name}.sqlite3-shm  (during writes)
```

### 5.2 SQLite Configuration

```python
# Connection settings for optimal FTS performance
SQLITE_PRAGMAS = {
    "journal_mode": "WAL",          # Write-Ahead Logging for concurrent reads
    "synchronous": "NORMAL",        # Balance durability and performance
    "cache_size": -64000,           # 64MB cache
    "temp_store": "MEMORY",         # In-memory temp tables
    "mmap_size": 268435456,         # 256MB memory-mapped I/O
}
```

### 5.3 Search Query Pattern

```sql
-- BM25-ranked search with snippet extraction
SELECT 
    chunk_id,
    source_title,
    text,
    bm25(chunks_fts, 1.0, 0.75) AS score,
    snippet(chunks_fts, 0, '<mark>', '</mark>', '...', 32) AS snippet
FROM chunks_fts
WHERE chunks_fts MATCH ?
ORDER BY score
LIMIT ?;
```

### 5.4 Rebuild Strategy

1. Create new SQLite file with `.tmp` suffix
2. Process all Knowledge Inputs sequentially
3. Atomic rename: `.tmp` → `.sqlite3`
4. Delete old file

---

## 6. LlamaIndex Integration Layer

### 6.1 Purpose

LlamaIndex serves as the **integration layer**, not the architecture owner.

**What LlamaIndex provides:**
- Common interface across storage backends
- Text extraction utilities
- Chunking strategies
- Future backend adapters (Chroma, pgvector, etc.)

**What Huf owns:**
- Knowledge lifecycle
- Permissions
- Agent binding
- Mandatory vs optional knowledge
- Ingestion orchestration
- Prompt injection policy

### 6.2 LlamaIndex Components Used

```python
# Phase 1 LlamaIndex usage
from llama_index.core import Document
from llama_index.core.node_parser import SentenceSplitter
from llama_index.readers.file import (
    PDFReader,
    DocxReader,
    UnstructuredReader,
)

# Future phases will add:
# from llama_index.vector_stores.chroma import ChromaVectorStore
# from llama_index.embeddings.openai import OpenAIEmbedding
```

### 6.3 Abstraction Layer

**File**: `huf/ai/knowledge/backends/__init__.py`

```python
"""
Knowledge Backend Abstraction

This module provides a unified interface for knowledge storage backends.
Phase 1: SQLite FTS only
Future: Chroma, pgvector, managed vector DBs
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class ChunkResult:
    """Result from a knowledge search."""
    chunk_id: str
    text: str
    title: Optional[str] = None
    score: float = 0.0
    source: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class KnowledgeBackend(ABC):
    """Abstract base class for knowledge backends."""
    
    @abstractmethod
    def initialize(self, knowledge_source: str, config: Dict[str, Any]) -> None:
        """Initialize the backend for a knowledge source."""
        pass
    
    @abstractmethod
    def add_chunks(self, chunks: List[Dict[str, Any]]) -> int:
        """Add chunks to the backend. Returns number added."""
        pass
    
    @abstractmethod
    def delete_chunks(self, input_id: str) -> int:
        """Delete all chunks for an input. Returns number deleted."""
        pass
    
    @abstractmethod
    def search(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[ChunkResult]:
        """Search for relevant chunks."""
        pass
    
    @abstractmethod
    def clear(self) -> None:
        """Clear all chunks from the backend."""
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """Get backend statistics (chunk count, size, etc.)."""
        pass


def get_backend(backend_type: str) -> type:
    """Get backend class by type."""
    backends = {
        "sqlite_fts": "huf.ai.knowledge.backends.sqlite_fts.SQLiteFTSBackend",
        # Future backends:
        # "chroma": "huf.ai.knowledge.backends.chroma.ChromaBackend",
        # "pgvector": "huf.ai.knowledge.backends.pgvector.PgVectorBackend",
    }
    
    if backend_type not in backends:
        raise ValueError(f"Unknown backend type: {backend_type}")
    
    import frappe
    return frappe.get_attr(backends[backend_type])
```

### 6.4 SQLite FTS Backend

**File**: `huf/ai/knowledge/backends/sqlite_fts.py`

```python
"""SQLite FTS5 Backend for Knowledge System."""

import os
import sqlite3
import json
import uuid
from typing import List, Dict, Any, Optional
from contextlib import contextmanager

import frappe
from frappe.utils import get_files_path

from . import KnowledgeBackend, ChunkResult


class SQLiteFTSBackend(KnowledgeBackend):
    """SQLite FTS5 backend for keyword search."""
    
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS chunks (
        chunk_id TEXT PRIMARY KEY,
        input_id TEXT NOT NULL,
        input_type TEXT NOT NULL,
        source_title TEXT,
        chunk_index INTEGER NOT NULL,
        text TEXT NOT NULL,
        char_start INTEGER,
        char_end INTEGER,
        metadata TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
        text,
        source_title,
        content='chunks',
        content_rowid='rowid',
        tokenize='porter unicode61'
    );
    
    CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
        INSERT INTO chunks_fts(rowid, text, source_title) 
        VALUES (new.rowid, new.text, new.source_title);
    END;
    
    CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
        INSERT INTO chunks_fts(chunks_fts, rowid, text, source_title) 
        VALUES ('delete', old.rowid, old.text, old.source_title);
    END;
    
    CREATE INDEX IF NOT EXISTS idx_chunks_input_id ON chunks(input_id);
    """
    
    PRAGMAS = {
        "journal_mode": "WAL",
        "synchronous": "NORMAL",
        "cache_size": -64000,
        "temp_store": "MEMORY",
    }
    
    def __init__(self):
        self.knowledge_source = None
        self.db_path = None
        self._config = {}
    
    def initialize(self, knowledge_source: str, config: Dict[str, Any]) -> None:
        """Initialize SQLite database for knowledge source."""
        self.knowledge_source = knowledge_source
        self._config = config
        
        # Determine database path
        files_path = get_files_path(is_private=True)
        knowledge_dir = os.path.join(files_path, "knowledge")
        os.makedirs(knowledge_dir, exist_ok=True)
        
        # Sanitize name for filesystem
        safe_name = frappe.scrub(knowledge_source)
        self.db_path = os.path.join(knowledge_dir, f"{safe_name}.sqlite3")
        
        # Create database and schema
        with self._get_connection() as conn:
            conn.executescript(self.SCHEMA)
    
    @contextmanager
    def _get_connection(self, readonly: bool = False):
        """Get SQLite connection with proper settings."""
        mode = "ro" if readonly else "rwc"
        uri = f"file:{self.db_path}?mode={mode}"
        
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        
        try:
            # Apply pragmas
            for pragma, value in self.PRAGMAS.items():
                conn.execute(f"PRAGMA {pragma} = {value}")
            
            yield conn
            
            if not readonly:
                conn.commit()
        except Exception:
            if not readonly:
                conn.rollback()
            raise
        finally:
            conn.close()
    
    def add_chunks(self, chunks: List[Dict[str, Any]]) -> int:
        """Add chunks to the database."""
        if not chunks:
            return 0
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            for chunk in chunks:
                chunk_id = chunk.get("chunk_id") or str(uuid.uuid4())
                metadata = json.dumps(chunk.get("metadata", {}))
                
                cursor.execute("""
                    INSERT OR REPLACE INTO chunks 
                    (chunk_id, input_id, input_type, source_title, chunk_index, 
                     text, char_start, char_end, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    chunk_id,
                    chunk["input_id"],
                    chunk["input_type"],
                    chunk.get("source_title"),
                    chunk["chunk_index"],
                    chunk["text"],
                    chunk.get("char_start"),
                    chunk.get("char_end"),
                    metadata,
                ))
            
            return len(chunks)
    
    def delete_chunks(self, input_id: str) -> int:
        """Delete all chunks for an input."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM chunks WHERE input_id = ?",
                (input_id,)
            )
            return cursor.rowcount
    
    def search(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[ChunkResult]:
        """Search using FTS5 with BM25 ranking."""
        if not query or not query.strip():
            return []
        
        # Escape special FTS5 characters
        safe_query = self._escape_fts_query(query)
        
        with self._get_connection(readonly=True) as conn:
            cursor = conn.execute("""
                SELECT 
                    c.chunk_id,
                    c.text,
                    c.source_title,
                    c.input_id,
                    c.metadata,
                    bm25(chunks_fts, 1.0, 0.75) AS score
                FROM chunks_fts
                JOIN chunks c ON chunks_fts.rowid = c.rowid
                WHERE chunks_fts MATCH ?
                ORDER BY score
                LIMIT ?
            """, (safe_query, top_k))
            
            results = []
            for row in cursor.fetchall():
                metadata = {}
                if row["metadata"]:
                    try:
                        metadata = json.loads(row["metadata"])
                    except json.JSONDecodeError:
                        pass
                
                results.append(ChunkResult(
                    chunk_id=row["chunk_id"],
                    text=row["text"],
                    title=row["source_title"],
                    score=abs(row["score"]),  # BM25 returns negative scores
                    source=row["input_id"],
                    metadata=metadata,
                ))
            
            return results
    
    def _escape_fts_query(self, query: str) -> str:
        """Escape special characters for FTS5 query."""
        # Remove problematic characters
        special_chars = ['"', "'", "(", ")", "*", ":", "^", "-", "+"]
        result = query
        for char in special_chars:
            result = result.replace(char, " ")
        
        # Split into terms and wrap in quotes for phrase-like matching
        terms = result.split()
        if len(terms) > 1:
            return " OR ".join(f'"{term}"' for term in terms if term)
        return result
    
    def clear(self) -> None:
        """Clear all chunks from the database."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM chunks")
            conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        stats = {
            "chunk_count": 0,
            "input_count": 0,
            "size_bytes": 0,
        }
        
        if not os.path.exists(self.db_path):
            return stats
        
        stats["size_bytes"] = os.path.getsize(self.db_path)
        
        with self._get_connection(readonly=True) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM chunks")
            stats["chunk_count"] = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(DISTINCT input_id) FROM chunks")
            stats["input_count"] = cursor.fetchone()[0]
        
        return stats
```

---

## 7. Core Python Modules

### 7.1 Module Structure

```
huf/ai/knowledge/
├── __init__.py
├── backends/
│   ├── __init__.py          # KnowledgeBackend ABC
│   ├── sqlite_fts.py        # SQLite FTS5 implementation
│   └── (future: chroma.py, pgvector.py)
├── extractors/
│   ├── __init__.py          # TextExtractor ABC
│   ├── pdf.py               # PDF extraction
│   ├── docx.py              # DOCX extraction
│   ├── text.py              # Plain text / markdown
│   └── html.py              # HTML extraction
├── chunkers/
│   ├── __init__.py          # Chunker ABC
│   └── sentence.py          # Sentence-aware chunking
├── indexer.py               # Ingestion pipeline
├── retriever.py             # Search & retrieval
├── tool.py                  # knowledge_search tool for agents
└── context_builder.py       # Build context for agent prompts
```

### 7.2 Text Extractors

**File**: `huf/ai/knowledge/extractors/__init__.py`

```python
"""Text extraction from various file formats."""

from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass


@dataclass
class ExtractedText:
    """Result of text extraction."""
    text: str
    title: Optional[str] = None
    metadata: Optional[dict] = None
    character_count: int = 0


class TextExtractor(ABC):
    """Abstract base class for text extractors."""
    
    @abstractmethod
    def extract(self, file_path: str) -> ExtractedText:
        """Extract text from file."""
        pass
    
    @staticmethod
    def get_extractor(file_type: str) -> "TextExtractor":
        """Get appropriate extractor for file type."""
        extractors = {
            "application/pdf": "huf.ai.knowledge.extractors.pdf.PDFExtractor",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": 
                "huf.ai.knowledge.extractors.docx.DocxExtractor",
            "text/plain": "huf.ai.knowledge.extractors.text.TextExtractor",
            "text/markdown": "huf.ai.knowledge.extractors.text.TextExtractor",
            "text/html": "huf.ai.knowledge.extractors.html.HTMLExtractor",
        }
        
        import frappe
        extractor_path = extractors.get(file_type, extractors["text/plain"])
        return frappe.get_attr(extractor_path)()
```

### 7.3 Chunking Strategy

**File**: `huf/ai/knowledge/chunkers/sentence.py`

```python
"""Sentence-aware text chunking."""

from typing import List, Dict, Any
from dataclasses import dataclass


@dataclass
class Chunk:
    """A text chunk with position information."""
    text: str
    chunk_index: int
    char_start: int
    char_end: int


def chunk_text(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 50,
) -> List[Chunk]:
    """
    Split text into overlapping chunks, respecting sentence boundaries.
    
    Uses LlamaIndex's SentenceSplitter under the hood for optimal chunking.
    """
    try:
        from llama_index.core.node_parser import SentenceSplitter
        
        splitter = SentenceSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        
        # LlamaIndex expects Document objects
        from llama_index.core import Document
        doc = Document(text=text)
        nodes = splitter.get_nodes_from_documents([doc])
        
        chunks = []
        for i, node in enumerate(nodes):
            chunks.append(Chunk(
                text=node.text,
                chunk_index=i,
                char_start=node.start_char_idx or 0,
                char_end=node.end_char_idx or len(node.text),
            ))
        
        return chunks
        
    except ImportError:
        # Fallback to simple chunking if LlamaIndex not available
        return _simple_chunk(text, chunk_size, chunk_overlap)


def _simple_chunk(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
) -> List[Chunk]:
    """Simple fallback chunker without sentence awareness."""
    chunks = []
    start = 0
    chunk_index = 0
    
    while start < len(text):
        end = min(start + chunk_size, len(text))
        
        # Try to break at sentence boundary
        if end < len(text):
            for sep in [". ", "! ", "? ", "\n\n", "\n"]:
                last_sep = text.rfind(sep, start, end)
                if last_sep > start + chunk_size // 2:
                    end = last_sep + len(sep)
                    break
        
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append(Chunk(
                text=chunk_text,
                chunk_index=chunk_index,
                char_start=start,
                char_end=end,
            ))
            chunk_index += 1
        
        start = end - chunk_overlap
        if start >= len(text) - chunk_overlap:
            break
    
    return chunks
```

---

## 8. Ingestion Pipeline

### 8.1 Process Flow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ Knowledge Input │────▶│  Text Extract   │────▶│    Chunking     │
│   (trigger)     │     │  (file type)    │     │  (configurable) │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                         │
                                                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Update Stats   │◀────│  Update Status  │◀────│  Insert SQLite  │
│   & Metadata    │     │   (Indexed)     │     │    (chunks)     │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

### 8.2 Indexer Implementation

**File**: `huf/ai/knowledge/indexer.py`

```python
"""Knowledge ingestion and indexing pipeline."""

import os
import frappe
from frappe import _
from frappe.utils import now_datetime, get_files_path

from .backends import get_backend
from .extractors import TextExtractor, ExtractedText
from .chunkers.sentence import chunk_text


def process_knowledge_input(knowledge_input: str) -> dict:
    """
    Process a single knowledge input and add to index.
    
    This function is designed to run in a background job.
    """
    doc = frappe.get_doc("Knowledge Input", knowledge_input)
    source = frappe.get_doc("Knowledge Source", doc.knowledge_source)
    
    try:
        # Update status
        doc.status = "Processing"
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        
        # Acquire lock for this knowledge source
        lock_key = f"knowledge_index_{source.name}"
        if not frappe.cache.add(lock_key, 1, expires_in_sec=300):
            raise Exception(_("Another indexing operation is in progress"))
        
        try:
            # Extract text
            extracted = _extract_text(doc)
            
            # Chunk text
            chunks = chunk_text(
                text=extracted.text,
                chunk_size=source.chunk_size or 512,
                chunk_overlap=source.chunk_overlap or 50,
            )
            
            # Prepare chunk data
            chunk_data = []
            for chunk in chunks:
                chunk_data.append({
                    "input_id": doc.name,
                    "input_type": doc.input_type,
                    "source_title": extracted.title or doc.file_name,
                    "chunk_index": chunk.chunk_index,
                    "text": chunk.text,
                    "char_start": chunk.char_start,
                    "char_end": chunk.char_end,
                    "metadata": extracted.metadata,
                })
            
            # Initialize backend and add chunks
            backend_class = get_backend(source.knowledge_type)
            backend = backend_class()
            backend.initialize(source.name, {
                "chunk_size": source.chunk_size,
                "chunk_overlap": source.chunk_overlap,
            })
            
            # Delete existing chunks for this input (for reprocessing)
            backend.delete_chunks(doc.name)
            
            # Add new chunks
            chunks_added = backend.add_chunks(chunk_data)
            
            # Update input status
            doc.status = "Indexed"
            doc.chunks_created = chunks_added
            doc.character_count = extracted.character_count
            doc.processed_at = now_datetime()
            doc.error_message = None
            doc.save(ignore_permissions=True)
            
            # Update source stats
            _update_source_stats(source, backend)
            
            frappe.db.commit()
            
            return {
                "status": "success",
                "chunks_created": chunks_added,
                "character_count": extracted.character_count,
            }
            
        finally:
            frappe.cache.delete(lock_key)
            
    except Exception as e:
        frappe.db.rollback()
        
        doc.reload()
        doc.status = "Error"
        doc.error_message = str(e)[:500]
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        
        frappe.log_error(
            f"Knowledge Input Processing Error: {doc.name}",
            frappe.get_traceback()
        )
        
        return {
            "status": "error",
            "error": str(e),
        }


def rebuild_knowledge_index(knowledge_source: str) -> dict:
    """
    Rebuild entire index for a knowledge source.
    
    This function is designed to run in a background job.
    """
    source = frappe.get_doc("Knowledge Source", knowledge_source)
    
    try:
        # Acquire exclusive lock
        lock_key = f"knowledge_index_{source.name}"
        if not frappe.cache.add(lock_key, 1, expires_in_sec=600):
            raise Exception(_("Another indexing operation is in progress"))
        
        try:
            source.status = "Rebuilding"
            source.save(ignore_permissions=True)
            frappe.db.commit()
            
            # Initialize backend and clear
            backend_class = get_backend(source.knowledge_type)
            backend = backend_class()
            backend.initialize(source.name, {
                "chunk_size": source.chunk_size,
                "chunk_overlap": source.chunk_overlap,
            })
            backend.clear()
            
            # Reset all input statuses
            frappe.db.sql("""
                UPDATE `tabKnowledge Input`
                SET status = 'Pending', chunks_created = 0
                WHERE knowledge_source = %s
            """, source.name)
            frappe.db.commit()
            
            # Process each input
            inputs = frappe.get_all(
                "Knowledge Input",
                filters={"knowledge_source": source.name},
                pluck="name"
            )
            
            total_chunks = 0
            for input_name in inputs:
                result = process_knowledge_input(input_name)
                if result.get("status") == "success":
                    total_chunks += result.get("chunks_created", 0)
            
            # Update source status
            _update_source_stats(source, backend)
            source.reload()
            source.status = "Ready"
            source.last_indexed_at = now_datetime()
            source.save(ignore_permissions=True)
            frappe.db.commit()
            
            return {
                "status": "success",
                "total_chunks": total_chunks,
                "inputs_processed": len(inputs),
            }
            
        finally:
            frappe.cache.delete(lock_key)
            
    except Exception as e:
        frappe.db.rollback()
        
        source.reload()
        source.status = "Error"
        source.error_message = str(e)[:500]
        source.save(ignore_permissions=True)
        frappe.db.commit()
        
        frappe.log_error(
            f"Knowledge Index Rebuild Error: {source.name}",
            frappe.get_traceback()
        )
        
        return {
            "status": "error",
            "error": str(e),
        }


def _extract_text(doc) -> ExtractedText:
    """Extract text from a Knowledge Input document."""
    if doc.input_type == "Text":
        return ExtractedText(
            text=doc.text,
            title="Pasted Text",
            character_count=len(doc.text or ""),
        )
    
    elif doc.input_type == "File":
        # Get file path
        file_doc = frappe.get_doc("File", {"file_url": doc.file})
        file_path = file_doc.get_full_path()
        
        # Get appropriate extractor
        extractor = TextExtractor.get_extractor(doc.file_type)
        return extractor.extract(file_path)
    
    elif doc.input_type == "URL":
        # URL extraction (future enhancement)
        raise NotImplementedError("URL extraction not yet implemented")
    
    raise ValueError(f"Unknown input type: {doc.input_type}")


def _update_source_stats(source, backend):
    """Update knowledge source statistics."""
    stats = backend.get_stats()
    
    source.reload()
    source.total_chunks = stats.get("chunk_count", 0)
    source.total_inputs = stats.get("input_count", 0)
    source.index_size_bytes = stats.get("size_bytes", 0)
    source.sqlite_file_path = backend.db_path
    source.save(ignore_permissions=True)
```

---

## 9. Retrieval System

### 9.1 Retriever Implementation

**File**: `huf/ai/knowledge/retriever.py`

```python
"""Knowledge retrieval system."""

from typing import List, Dict, Any, Optional
import frappe
from frappe import _

from .backends import get_backend, ChunkResult


@frappe.whitelist()
def knowledge_search(
    query: str,
    knowledge_source: Optional[str] = None,
    knowledge_sources: Optional[List[str]] = None,
    top_k: int = 5,
    filters: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Search for relevant knowledge chunks.
    
    This is the main retrieval contract used by agents.
    
    Args:
        query: The search query
        knowledge_source: Single knowledge source to search
        knowledge_sources: Multiple knowledge sources to search
        top_k: Maximum results per source
        filters: Additional filters (reserved for future use)
    
    Returns:
        List of chunk results with text, title, score, and source
    """
    if not query or not query.strip():
        return []
    
    # Determine sources to search
    sources = []
    if knowledge_source:
        sources = [knowledge_source]
    elif knowledge_sources:
        sources = knowledge_sources
    else:
        frappe.throw(_("Either knowledge_source or knowledge_sources is required"))
    
    # Collect results from all sources
    all_results = []
    
    for source_name in sources:
        try:
            source = frappe.get_doc("Knowledge Source", source_name)
            
            # Check if source is ready
            if source.status != "Ready":
                continue
            
            if source.disabled:
                continue
            
            # Initialize backend
            backend_class = get_backend(source.knowledge_type)
            backend = backend_class()
            backend.initialize(source_name, {})
            
            # Search
            results = backend.search(query, top_k=top_k, filters=filters)
            
            # Add source information
            for result in results:
                all_results.append({
                    "text": result.text,
                    "title": result.title,
                    "score": result.score,
                    "chunk_id": result.chunk_id,
                    "source": source_name,
                    "metadata": result.metadata,
                })
                
        except Exception as e:
            frappe.log_error(
                f"Knowledge search error for {source_name}",
                frappe.get_traceback()
            )
            continue
    
    # Sort by score across all sources
    all_results.sort(key=lambda x: x["score"], reverse=True)
    
    # Limit to top_k total
    return all_results[:top_k]


def get_mandatory_knowledge(agent_name: str) -> List[Dict[str, Any]]:
    """
    Get mandatory knowledge sources for an agent.
    
    Returns list of knowledge source configurations with mode='Mandatory'.
    """
    agent = frappe.get_doc("Agent", agent_name)
    
    mandatory_sources = []
    for ak in agent.get("agent_knowledge", []):
        if ak.mode == "Mandatory":
            mandatory_sources.append({
                "knowledge_source": ak.knowledge_source,
                "priority": ak.priority or 0,
                "max_chunks": ak.max_chunks or 5,
                "token_budget": ak.token_budget or 2000,
            })
    
    # Sort by priority (higher first)
    mandatory_sources.sort(key=lambda x: x["priority"], reverse=True)
    
    return mandatory_sources


def get_optional_knowledge(agent_name: str) -> List[Dict[str, Any]]:
    """
    Get optional knowledge sources for an agent.
    
    Returns list of knowledge source configurations with mode='Optional'.
    """
    agent = frappe.get_doc("Agent", agent_name)
    
    optional_sources = []
    for ak in agent.get("agent_knowledge", []):
        if ak.mode == "Optional":
            optional_sources.append({
                "knowledge_source": ak.knowledge_source,
                "priority": ak.priority or 0,
                "max_chunks": ak.max_chunks or 5,
                "token_budget": ak.token_budget or 2000,
            })
    
    return optional_sources
```

---

## 10. Agent Integration

### 10.1 Agent DocType Updates

Add new child table field to Agent DocType:

**File**: `huf/huf/doctype/agent/agent.json` (additions)

```json
{
  "fieldname": "knowledge_tab",
  "fieldtype": "Tab Break",
  "label": "Knowledge"
},
{
  "fieldname": "agent_knowledge",
  "fieldtype": "Table",
  "label": "Knowledge Sources",
  "options": "Agent Knowledge",
  "description": "Knowledge sources this agent can access"
}
```

### 10.2 Knowledge Context Builder

**File**: `huf/ai/knowledge/context_builder.py`

```python
"""Build knowledge context for agent prompts."""

from typing import List, Dict, Any, Optional
import frappe

from .retriever import knowledge_search, get_mandatory_knowledge


def build_knowledge_context(
    agent_name: str,
    user_query: str,
    max_tokens: int = 4000,
) -> Dict[str, Any]:
    """
    Build knowledge context to inject into agent prompt.
    
    This is called for mandatory knowledge sources before agent execution.
    
    Args:
        agent_name: Name of the agent
        user_query: The user's query (used for search)
        max_tokens: Maximum tokens for knowledge context
    
    Returns:
        Dict with 'context_text', 'sources_used', 'chunks_used'
    """
    mandatory_sources = get_mandatory_knowledge(agent_name)
    
    if not mandatory_sources:
        return {
            "context_text": "",
            "sources_used": [],
            "chunks_used": [],
        }
    
    all_chunks = []
    sources_used = []
    
    for source_config in mandatory_sources:
        source_name = source_config["knowledge_source"]
        max_chunks = source_config["max_chunks"]
        
        try:
            results = knowledge_search(
                query=user_query,
                knowledge_source=source_name,
                top_k=max_chunks,
            )
            
            if results:
                all_chunks.extend(results)
                sources_used.append(source_name)
                
        except Exception as e:
            frappe.log_error(
                f"Knowledge context error for {source_name}",
                frappe.get_traceback()
            )
    
    if not all_chunks:
        return {
            "context_text": "",
            "sources_used": [],
            "chunks_used": [],
        }
    
    # Build context text with source attribution
    context_parts = ["## Relevant Knowledge\n"]
    chunks_used = []
    estimated_tokens = 0
    
    for chunk in all_chunks:
        # Rough token estimation (4 chars per token)
        chunk_tokens = len(chunk["text"]) // 4
        
        if estimated_tokens + chunk_tokens > max_tokens:
            break
        
        context_parts.append(f"### {chunk.get('title', 'Source')}\n")
        context_parts.append(chunk["text"])
        context_parts.append("\n\n")
        
        chunks_used.append({
            "chunk_id": chunk["chunk_id"],
            "source": chunk["source"],
            "title": chunk.get("title"),
        })
        
        estimated_tokens += chunk_tokens
    
    return {
        "context_text": "".join(context_parts),
        "sources_used": sources_used,
        "chunks_used": chunks_used,
    }


def inject_knowledge_context(
    prompt: str,
    knowledge_context: Dict[str, Any],
) -> str:
    """
    Inject knowledge context into the agent prompt.
    
    Places knowledge before the user's message.
    """
    if not knowledge_context.get("context_text"):
        return prompt
    
    context_text = knowledge_context["context_text"]
    
    # Insert context before the prompt
    return f"{context_text}\n---\n\n{prompt}"
```

### 10.3 Knowledge Search Tool

**File**: `huf/ai/knowledge/tool.py`

```python
"""Knowledge search tool for agent use."""

import frappe
from typing import Optional

from .retriever import knowledge_search


def create_knowledge_search_tool(agent_name: str) -> dict:
    """
    Create a knowledge_search tool definition for an agent.
    
    This tool allows agents to optionally search knowledge sources.
    """
    # Get optional knowledge sources for this agent
    agent = frappe.get_doc("Agent", agent_name)
    optional_sources = []
    
    for ak in agent.get("agent_knowledge", []):
        if ak.mode == "Optional":
            optional_sources.append(ak.knowledge_source)
    
    if not optional_sources:
        return None
    
    # Build tool definition
    return {
        "tool_name": "knowledge_search",
        "description": f"""Search the agent's knowledge base for relevant information.
        
Available knowledge sources: {', '.join(optional_sources)}

Use this tool when you need to find specific information from the knowledge base.
Always cite the source when using information from search results.""",
        "parameters": [
            {
                "label": "Query",
                "fieldname": "query",
                "type": "string",
                "required": True,
                "description": "The search query to find relevant information",
            },
            {
                "label": "Knowledge Source",
                "fieldname": "knowledge_source",
                "type": "string",
                "required": False,
                "description": f"Specific knowledge source to search. Options: {', '.join(optional_sources)}",
            },
            {
                "label": "Top K",
                "fieldname": "top_k",
                "type": "integer",
                "required": False,
                "description": "Maximum number of results to return (default: 5)",
            },
        ],
    }


async def handle_knowledge_search(
    agent_name: str,
    query: str,
    knowledge_source: Optional[str] = None,
    top_k: int = 5,
) -> str:
    """
    Handle knowledge_search tool call from agent.
    
    Returns formatted search results.
    """
    # Validate that agent has access to this source
    if knowledge_source:
        agent = frappe.get_doc("Agent", agent_name)
        allowed_sources = [
            ak.knowledge_source 
            for ak in agent.get("agent_knowledge", [])
            if ak.mode == "Optional"
        ]
        
        if knowledge_source not in allowed_sources:
            return f"Error: Knowledge source '{knowledge_source}' is not available."
    else:
        # Search all optional sources
        agent = frappe.get_doc("Agent", agent_name)
        sources = [
            ak.knowledge_source 
            for ak in agent.get("agent_knowledge", [])
            if ak.mode == "Optional"
        ]
        knowledge_source = sources[0] if len(sources) == 1 else None
    
    # Perform search
    try:
        results = knowledge_search(
            query=query,
            knowledge_source=knowledge_source,
            top_k=top_k,
        )
        
        if not results:
            return "No relevant results found for your query."
        
        # Format results
        output = []
        for i, result in enumerate(results, 1):
            output.append(f"## Result {i}: {result.get('title', 'Untitled')}")
            output.append(f"Source: {result['source']}")
            output.append(f"Score: {result['score']:.3f}")
            output.append("")
            output.append(result["text"])
            output.append("")
            output.append("---")
            output.append("")
        
        return "\n".join(output)
        
    except Exception as e:
        return f"Error searching knowledge base: {str(e)}"
```

### 10.4 Integration with Agent Run

Modify `agent_integration.py` to include knowledge context:

```python
# In run_agent_sync, before calling the provider:

# Build knowledge context for mandatory sources
from huf.ai.knowledge.context_builder import build_knowledge_context, inject_knowledge_context

knowledge_context = build_knowledge_context(
    agent_name=agent_name,
    user_query=prompt,
)

# Inject context into prompt
enhanced_prompt = inject_knowledge_context(prompt, knowledge_context)

# Store knowledge usage in run document
if knowledge_context.get("sources_used"):
    run_doc.knowledge_sources_used = json.dumps(knowledge_context["sources_used"])
    run_doc.chunks_injected = len(knowledge_context.get("chunks_used", []))
```

---

## 11. Hooks & Events

### 11.1 Document Events

**File**: `huf/hooks.py` (additions)

```python
doc_events = {
    # ... existing events ...
    
    "Knowledge Source": {
        "after_insert": "huf.ai.knowledge.hooks.on_knowledge_source_created",
        "on_update": "huf.ai.knowledge.hooks.on_knowledge_source_updated",
        "on_trash": "huf.ai.knowledge.hooks.on_knowledge_source_deleted",
    },
    "Knowledge Input": {
        "after_insert": "huf.ai.knowledge.hooks.on_knowledge_input_created",
        "on_trash": "huf.ai.knowledge.hooks.on_knowledge_input_deleted",
    },
}
```

### 11.2 Hook Implementations

**File**: `huf/ai/knowledge/hooks.py`

```python
"""Document event hooks for knowledge system."""

import frappe


def on_knowledge_source_created(doc, method):
    """Initialize knowledge source after creation."""
    # Initialize SQLite database
    from .backends import get_backend
    
    backend_class = get_backend(doc.knowledge_type)
    backend = backend_class()
    backend.initialize(doc.name, {
        "chunk_size": doc.chunk_size,
        "chunk_overlap": doc.chunk_overlap,
    })


def on_knowledge_source_updated(doc, method):
    """Handle knowledge source updates."""
    # Check if chunking settings changed
    old_doc = doc.get_doc_before_save()
    if old_doc:
        if (old_doc.chunk_size != doc.chunk_size or 
            old_doc.chunk_overlap != doc.chunk_overlap):
            # Chunking changed - suggest rebuild
            frappe.msgprint(
                "Chunking settings changed. Consider rebuilding the index.",
                alert=True
            )


def on_knowledge_source_deleted(doc, method):
    """Cleanup when knowledge source is deleted."""
    # Delete SQLite file
    import os
    from frappe.utils import get_files_path
    
    files_path = get_files_path(is_private=True)
    safe_name = frappe.scrub(doc.name)
    db_path = os.path.join(files_path, "knowledge", f"{safe_name}.sqlite3")
    
    if os.path.exists(db_path):
        os.remove(db_path)
    
    # Also remove WAL and SHM files if they exist
    for ext in ["-wal", "-shm"]:
        wal_path = db_path + ext
        if os.path.exists(wal_path):
            os.remove(wal_path)


def on_knowledge_input_created(doc, method):
    """Queue processing when input is created."""
    # Processing is already queued in after_insert of the DocType
    pass


def on_knowledge_input_deleted(doc, method):
    """Remove chunks when input is deleted."""
    from .backends import get_backend
    
    source = frappe.get_doc("Knowledge Source", doc.knowledge_source)
    
    backend_class = get_backend(source.knowledge_type)
    backend = backend_class()
    backend.initialize(source.name, {})
    backend.delete_chunks(doc.name)
    
    # Update source stats
    stats = backend.get_stats()
    source.total_chunks = stats.get("chunk_count", 0)
    source.total_inputs = stats.get("input_count", 0)
    source.save(ignore_permissions=True)
```

### 11.3 Scheduler Events

**File**: `huf/hooks.py` (additions)

```python
scheduler_events = {
    # ... existing events ...
    
    "daily": [
        "huf.ai.knowledge.maintenance.cleanup_orphaned_files",
        "huf.ai.knowledge.maintenance.optimize_indexes",
    ],
}
```

### 11.4 Maintenance Tasks

**File**: `huf/ai/knowledge/maintenance.py`

```python
"""Maintenance tasks for knowledge system."""

import os
import frappe
from frappe.utils import get_files_path


def cleanup_orphaned_files():
    """Remove orphaned SQLite files without corresponding Knowledge Source."""
    files_path = get_files_path(is_private=True)
    knowledge_dir = os.path.join(files_path, "knowledge")
    
    if not os.path.exists(knowledge_dir):
        return
    
    # Get all existing knowledge sources
    existing_sources = set(
        frappe.scrub(name) 
        for name in frappe.get_all("Knowledge Source", pluck="name")
    )
    
    # Check each file in knowledge directory
    for filename in os.listdir(knowledge_dir):
        if filename.endswith(".sqlite3"):
            source_name = filename[:-8]  # Remove .sqlite3
            if source_name not in existing_sources:
                file_path = os.path.join(knowledge_dir, filename)
                os.remove(file_path)
                frappe.log_error(
                    f"Removed orphaned knowledge file: {filename}",
                    "Knowledge Maintenance"
                )


def optimize_indexes():
    """Optimize SQLite indexes for all knowledge sources."""
    import sqlite3
    
    sources = frappe.get_all(
        "Knowledge Source",
        filters={"status": "Ready", "disabled": 0},
        fields=["name", "sqlite_file_path"]
    )
    
    for source in sources:
        if source.sqlite_file_path and os.path.exists(source.sqlite_file_path):
            try:
                conn = sqlite3.connect(source.sqlite_file_path)
                conn.execute("PRAGMA optimize")
                conn.execute("VACUUM")
                conn.close()
            except Exception as e:
                frappe.log_error(
                    f"Error optimizing {source.name}: {str(e)}",
                    "Knowledge Maintenance"
                )
```

---

## 12. API Endpoints

### 12.1 Whitelisted Methods

| Endpoint | Method | Description |
|----------|--------|-------------|
| `huf.ai.knowledge.retriever.knowledge_search` | POST | Search knowledge sources |
| `huf.huf.doctype.knowledge_source.knowledge_source.rebuild_index` | POST | Trigger index rebuild |
| `huf.huf.doctype.knowledge_source.knowledge_source.test_search` | POST | Test search against source |
| `huf.huf.doctype.knowledge_input.knowledge_input.reprocess_input` | POST | Reprocess failed input |

### 12.2 REST API Examples

**Search Knowledge:**
```bash
curl -X POST https://site.com/api/method/huf.ai.knowledge.retriever.knowledge_search \
  -H "Authorization: token api_key:api_secret" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "how to configure settings",
    "knowledge_source": "Product Documentation",
    "top_k": 5
  }'
```

**Rebuild Index:**
```bash
curl -X POST https://site.com/api/method/huf.huf.doctype.knowledge_source.knowledge_source.rebuild_index \
  -H "Authorization: token api_key:api_secret" \
  -H "Content-Type: application/json" \
  -d '{
    "knowledge_source": "Product Documentation"
  }'
```

---

## 13. Background Jobs

### 13.1 Job Types

| Job | Queue | Timeout | Description |
|-----|-------|---------|-------------|
| `process_knowledge_input` | default | 5 min | Process single input file |
| `rebuild_knowledge_index` | long | 30 min | Rebuild entire index |
| `cleanup_orphaned_files` | default | 10 min | Daily cleanup task |
| `optimize_indexes` | long | 60 min | Daily optimization |

### 13.2 Job Deduplication

```python
# Use unique job IDs to prevent duplicate processing
frappe.enqueue(
    process_knowledge_input,
    queue="default",
    knowledge_input=doc.name,
    job_id=f"process_input_{doc.name}",  # Unique per input
    deduplicate=True,
)
```

### 13.3 Redis Locking

```python
# Single writer per knowledge source
lock_key = f"knowledge_index_{source.name}"
if not frappe.cache.add(lock_key, 1, expires_in_sec=300):
    raise Exception("Another indexing operation is in progress")

try:
    # ... indexing work ...
finally:
    frappe.cache.delete(lock_key)
```

---

## 14. Observability & Logging

### 14.1 Agent Run Extensions

Add fields to Agent Run DocType:

```json
{
  "fieldname": "knowledge_section",
  "fieldtype": "Section Break",
  "label": "Knowledge Usage"
},
{
  "fieldname": "knowledge_sources_used",
  "fieldtype": "JSON",
  "label": "Knowledge Sources Used",
  "read_only": 1
},
{
  "fieldname": "chunks_injected",
  "fieldtype": "Int",
  "label": "Chunks Injected",
  "read_only": 1
}
```

### 14.2 Logging Strategy

```python
# Use frappe.log_error for errors
frappe.log_error(
    title=f"Knowledge Input Processing Error: {doc.name}",
    message=frappe.get_traceback()
)

# Use frappe.logger for debug info
logger = frappe.logger("knowledge")
logger.info(f"Indexed {chunks_added} chunks for {doc.name}")
```

### 14.3 Metrics to Track

- **Indexing**: Time per input, chunks per input, error rate
- **Search**: Query latency, results per query, cache hit rate
- **Usage**: Chunks injected per run, knowledge sources accessed

---

## 15. Frontend Components

### 15.1 Knowledge Source List View

**File**: `huf/huf/doctype/knowledge_source/knowledge_source_list.js`

```javascript
frappe.listview_settings["Knowledge Source"] = {
    add_fields: ["status", "total_chunks", "disabled"],
    
    get_indicator(doc) {
        if (doc.disabled) {
            return [__("Disabled"), "gray", "disabled,=,1"];
        }
        
        const status_map = {
            "Ready": ["Ready", "green"],
            "Pending": ["Pending", "orange"],
            "Indexing": ["Indexing", "blue"],
            "Rebuilding": ["Rebuilding", "blue"],
            "Error": ["Error", "red"],
        };
        
        const [label, color] = status_map[doc.status] || ["Unknown", "gray"];
        return [__(label), color, `status,=,${doc.status}`];
    },
    
    formatters: {
        total_chunks(value) {
            return value ? frappe.utils.format_number(value) : "0";
        }
    }
};
```

### 15.2 Knowledge Input Quick Entry

**File**: `huf/huf/doctype/knowledge_input/knowledge_input_quick_entry.js`

```javascript
frappe.ui.form.KnowledgeInputQuickEntryForm = class extends frappe.ui.form.QuickEntryForm {
    constructor(doctype, after_insert) {
        super(doctype, after_insert);
    }
    
    render_dialog() {
        super.render_dialog();
        
        // Add paste text area
        this.dialog.fields_dict.text.$wrapper.find("textarea").attr({
            rows: 10,
            placeholder: __("Paste your text content here...")
        });
    }
};
```

---

## 16. Provider Extensibility

### 16.1 Adding New Backends

To add a new backend (e.g., Chroma):

1. Create backend class implementing `KnowledgeBackend`:

```python
# huf/ai/knowledge/backends/chroma.py
from . import KnowledgeBackend, ChunkResult

class ChromaBackend(KnowledgeBackend):
    def initialize(self, knowledge_source, config):
        # Initialize Chroma collection
        pass
    
    def add_chunks(self, chunks):
        # Add to Chroma
        pass
    
    def search(self, query, top_k, filters):
        # Search Chroma
        pass
    # ... etc
```

2. Register in backend factory:

```python
# huf/ai/knowledge/backends/__init__.py
backends = {
    "sqlite_fts": "huf.ai.knowledge.backends.sqlite_fts.SQLiteFTSBackend",
    "chroma": "huf.ai.knowledge.backends.chroma.ChromaBackend",  # New
}
```

3. Add to Knowledge Source options:

```json
{
  "fieldname": "knowledge_type",
  "options": "sqlite_fts\nchroma"
}
```

### 16.2 Adding New Extractors

To support new file types:

1. Create extractor class:

```python
# huf/ai/knowledge/extractors/xlsx.py
from . import TextExtractor, ExtractedText

class XLSXExtractor(TextExtractor):
    def extract(self, file_path):
        import openpyxl
        # Extract text from Excel
        pass
```

2. Register in extractor factory:

```python
# huf/ai/knowledge/extractors/__init__.py
extractors = {
    # ... existing ...
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": 
        "huf.ai.knowledge.extractors.xlsx.XLSXExtractor",
}
```

### 16.3 Hook Points for Apps

Apps can extend knowledge via hooks:

```python
# In app's hooks.py
huf_knowledge_backends = [
    "my_app.knowledge.custom_backend"
]

huf_knowledge_extractors = [
    "my_app.knowledge.custom_extractor"
]
```

---

## 17. Testing Strategy

### 17.1 Unit Tests

**File**: `huf/ai/knowledge/tests/test_chunking.py`

```python
import unittest
from huf.ai.knowledge.chunkers.sentence import chunk_text, Chunk


class TestChunking(unittest.TestCase):
    def test_basic_chunking(self):
        text = "This is a test. " * 100
        chunks = chunk_text(text, chunk_size=200, chunk_overlap=20)
        
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk.text), 250)  # Allow some overflow
    
    def test_empty_text(self):
        chunks = chunk_text("", chunk_size=200)
        self.assertEqual(len(chunks), 0)
    
    def test_small_text(self):
        text = "Short text."
        chunks = chunk_text(text, chunk_size=200)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].text, text)
```

### 17.2 Integration Tests

**File**: `huf/huf/doctype/knowledge_source/test_knowledge_source.py`

```python
import frappe
from frappe.tests import IntegrationTestCase


class TestKnowledgeSource(IntegrationTestCase):
    def setUp(self):
        self.source = frappe.get_doc({
            "doctype": "Knowledge Source",
            "source_name": f"Test Source {frappe.generate_hash()[:8]}",
            "knowledge_type": "sqlite_fts",
            "scope": "Site",
        }).insert()
    
    def tearDown(self):
        frappe.delete_doc("Knowledge Source", self.source.name, force=True)
    
    def test_create_knowledge_source(self):
        self.assertEqual(self.source.status, "Pending")
        self.assertEqual(self.source.chunk_size, 512)
    
    def test_add_input(self):
        inp = frappe.get_doc({
            "doctype": "Knowledge Input",
            "knowledge_source": self.source.name,
            "input_type": "Text",
            "text": "This is test content for indexing.",
        }).insert()
        
        # Wait for background job
        from huf.ai.knowledge.indexer import process_knowledge_input
        process_knowledge_input(inp.name)
        
        inp.reload()
        self.assertEqual(inp.status, "Indexed")
```

### 17.3 Test Data Fixtures

```json
{
  "Knowledge Source": [
    {
      "doctype": "Knowledge Source",
      "source_name": "Test Documentation",
      "knowledge_type": "sqlite_fts",
      "scope": "Site",
      "chunk_size": 512,
      "chunk_overlap": 50
    }
  ]
}
```

---

## 18. Migration & Rollout

### 18.1 Migration Steps

1. **Run bench migrate** - Creates new DocTypes
2. **Initialize LlamaIndex dependencies** - `uv add llama-index-core`
3. **Create knowledge directory** - Automatic on first use

### 18.2 Rollback Plan

1. Disable knowledge features via flag
2. Remove Agent Knowledge child rows
3. Delete Knowledge Source documents
4. Clean up SQLite files

### 18.3 Feature Flags

```python
# In frappe.conf or Agent Settings
enable_knowledge_system = True
knowledge_max_chunk_size = 1024
knowledge_max_sources_per_agent = 10
```

---

## 19. Future Phases

### Phase 1.5: Semi-Semantic FTS

Without vectors:
- Ingestion-time keyword tagging via LLM
- Query expansion
- Optional reranking (cross-encoder)

### Phase 2: Vector Embeddings

- Add embedding generation
- SQLite brute-force vectors
- Hybrid search (FTS + vectors)

### Phase 3: Scalable Backends

- Chroma integration
- pgvector integration
- Cloud vector DBs (Pinecone, Weaviate)

### Phase 4: Advanced Features

- Multi-modal (images, tables)
- Knowledge graphs
- Automatic refresh/sync
- Access control per knowledge source

---

## Appendix A: File Checklist

### New DocTypes

- [ ] `huf/huf/doctype/knowledge_source/knowledge_source.json`
- [ ] `huf/huf/doctype/knowledge_source/knowledge_source.py`
- [ ] `huf/huf/doctype/knowledge_source/knowledge_source.js`
- [ ] `huf/huf/doctype/knowledge_source/__init__.py`
- [ ] `huf/huf/doctype/knowledge_source/test_knowledge_source.py`
- [ ] `huf/huf/doctype/knowledge_input/knowledge_input.json`
- [ ] `huf/huf/doctype/knowledge_input/knowledge_input.py`
- [ ] `huf/huf/doctype/knowledge_input/__init__.py`
- [ ] `huf/huf/doctype/knowledge_input/test_knowledge_input.py`
- [ ] `huf/huf/doctype/agent_knowledge/agent_knowledge.json`
- [ ] `huf/huf/doctype/agent_knowledge/agent_knowledge.py`
- [ ] `huf/huf/doctype/agent_knowledge/__init__.py`

### Core Modules

- [ ] `huf/ai/knowledge/__init__.py`
- [ ] `huf/ai/knowledge/backends/__init__.py`
- [ ] `huf/ai/knowledge/backends/sqlite_fts.py`
- [ ] `huf/ai/knowledge/extractors/__init__.py`
- [ ] `huf/ai/knowledge/extractors/pdf.py`
- [ ] `huf/ai/knowledge/extractors/docx.py`
- [ ] `huf/ai/knowledge/extractors/text.py`
- [ ] `huf/ai/knowledge/extractors/html.py`
- [ ] `huf/ai/knowledge/chunkers/__init__.py`
- [ ] `huf/ai/knowledge/chunkers/sentence.py`
- [ ] `huf/ai/knowledge/indexer.py`
- [ ] `huf/ai/knowledge/retriever.py`
- [ ] `huf/ai/knowledge/tool.py`
- [ ] `huf/ai/knowledge/context_builder.py`
- [ ] `huf/ai/knowledge/hooks.py`
- [ ] `huf/ai/knowledge/maintenance.py`

### Modifications

- [ ] `huf/huf/doctype/agent/agent.json` - Add knowledge tab and child table
- [ ] `huf/huf/doctype/agent_run/agent_run.json` - Add knowledge tracking fields
- [ ] `huf/ai/agent_integration.py` - Integrate knowledge context
- [ ] `huf/ai/sdk_tools.py` - Add knowledge_search tool
- [ ] `huf/hooks.py` - Add knowledge doc events and scheduler

### Dependencies

- [ ] `pyproject.toml` - Add `llama-index-core`, `llama-index-readers-file`

---

## Appendix B: Dependencies

```toml
# pyproject.toml additions
[project]
dependencies = [
    # ... existing ...
    "llama-index-core>=0.10.0",
    "llama-index-readers-file>=0.1.0",
]

[project.optional-dependencies]
knowledge = [
    "llama-index-core>=0.10.0",
    "llama-index-readers-file>=0.1.0",
]
```

---

## Appendix C: Configuration Reference

### Agent Settings Fields

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `enable_knowledge_system` | Check | 1 | Enable/disable knowledge features |
| `default_chunk_size` | Int | 512 | Default chunk size for new sources |
| `default_chunk_overlap` | Int | 50 | Default overlap for new sources |
| `max_knowledge_sources_per_agent` | Int | 10 | Limit sources per agent |
| `max_chunks_per_search` | Int | 20 | Maximum chunks in single search |

---

*Document Version: 1.0*
*Last Updated: January 2026*
*Author: Huf Development Team*
