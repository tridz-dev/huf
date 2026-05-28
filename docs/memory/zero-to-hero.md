# HUF Memory Architecture: Zero to Hero

> **Who this is for:** Anyone new to the memory/knowledge area of HUF — engineers, contributors, or agents reading this cold. This document captures the full intellectual journey: where the ideas came from, what was tried, what was decided, and why. Read this before touching any memory-related code.

---

## 1. The problem we are solving

HUF started as a conversational AI platform. Agents talk to users, run tools, and produce results. But every conversation was a blank slate. Agents had no memory of what they'd learned, no way to build up preferences or patterns over time, and no way to carry useful facts from one session to the next.

This became a real limitation:

- A user tells an agent their preferences in one conversation. The agent has forgotten them in the next.
- An agent learns a reliable routing pattern after many runs. That learning disappears.
- Research done in one session cannot be made available as searchable knowledge for other agents.
- There is no way to say "this fact, learned from a conversation, should be considered authoritative at the site level."

The gap was: **HUF had Knowledge Sources (static documents, PDFs, URLs) and conversation-local working data, but nothing in between** — no layer for learned, scoped, evolving data that could optionally become searchable.

---

## 2. The reference systems that shaped the design

Before arriving at the current architecture, several external systems were studied carefully. Understanding these is essential for understanding why HUF's design looks the way it does.

### 2.1 Agno (formerly phidata)

Agno is an open-source Python framework for building multi-modal AI agents. It has a clean separation between:

- **Agent memory**: short-term per-session state
- **Agent knowledge**: structured, indexed, searchable content (PDFs, URLs, tables, text)
- **Agent storage**: long-term persistence of runs and sessions

Agno's knowledge system uses a `Knowledge` class with pluggable readers (PDFReader, URLReader, etc.) and vector stores (pgvector, Qdrant, Pinecone, LanceDB, etc.). It separates the *reader* (how you get text from a source) from the *store* (how you index and retrieve it).

**What HUF borrowed from Agno:**
- The concept of pluggable knowledge backends (sqlite_fts, sqlite_vec, chroma — all implement a common `KnowledgeBackend` ABC)
- The idea that agents should be able to search knowledge before responding
- The pattern of separating ingestion from retrieval

**What HUF did differently:**
- HUF wraps this in Frappe DocTypes (Knowledge Source, Knowledge Input) so it integrates with the rest of the platform's permissions, workflows, and UI
- HUF has a stronger multi-tenancy and scoping requirement (User, Role, Agent, Site, Global)

### 2.2 Hindsight (memory consolidation pattern)

Hindsight is a research-inspired design pattern for long-term agent memory. The core idea is three operations:

- **retain**: extract and save something worth remembering from a conversation
- **recall**: retrieve relevant memory when starting a new conversation
- **reflect**: periodically consolidate, deduplicate, and upgrade memory quality

Hindsight-style systems typically run as a background process after each conversation. A second LLM call (the "reflection agent") reads the transcript and decides what to save.

**What HUF borrowed from Hindsight:**
- The idea of a dedicated "learning agent" that reads transcripts and extracts memory
- The concept of a learning trigger (end of conversation, every N turns)
- The draft → review → active lifecycle for extracted memories

**What HUF is NOT doing (yet):**
- Hindsight's reflect step (periodic consolidation across many memories) is not implemented
- Automatic contradiction detection is not implemented
- Memory decay and supersession is manual, not automatic

### 2.3 Mem0 / MemGPT patterns

These systems maintain a dedicated memory layer that agents read from and write to during a conversation, with a structured schema for different memory types (episodic, semantic, procedural).

**What HUF borrowed:**
- The scoped record type model (Fact, Preference, Decision, Pattern, Research, Instruction)
- The importance score + confidence fields for quality filtering
- The visibility model (Private, Shared with Role, Site, Global)

---

## 3. How HUF's existing knowledge system works

Before memory makes sense, you need to understand knowledge. Here is the actual pipeline:

```
Knowledge Source (DocType)
├── knowledge_type: sqlite_fts | sqlite_vec | chroma
├── embedding_model (for vector backends)
└── Knowledge Inputs []
    ├── input_type: Text | File | URL
    ├── status: Pending | Processing | Indexed | Error
    └── text / file / url content

Indexing pipeline (huf/ai/knowledge/indexer.py):
  Knowledge Input → extract text → chunk → embed (if vector) → store in backend

Retrieval pipeline (huf/ai/knowledge/retriever.py):
  query → embed query → search backend → return ChunkResult[]
```

**Three backends exist today, all implementing `KnowledgeBackend` ABC:**

| Backend | Type | When to use | Dependencies |
|---------|------|-------------|--------------|
| `sqlite_fts` | Keyword (BM25) | Always available, no GPU needed | None |
| `sqlite_vec` | Vector (semantic) | When you need semantic similarity | pysqlite3-binary + sqlite-vec |
| `chroma` | Vector (semantic) | When you want a separate vector store, optionally server-mode | chromadb + llama-index |

**Adding a new backend** (e.g., pg_vector) means:
1. Implement `KnowledgeBackend` ABC in `huf/ai/knowledge/backends/`
2. Register it in `get_backend()` in `__init__.py`
3. Add the option to Knowledge Source's `knowledge_type` Select field

The memory layer **never needs to change** when backends are added or removed.

---

## 4. The memory architecture

### 4.1 The three-layer model

```
┌─────────────────────────────────────────────────────────────────────┐
│  Conversation Data (temporary, per-session)                         │
│  → selected items, form values, current state, agent working memory │
│  → lives in Agent Conversation / run context only                   │
└────────────────────────────┬────────────────────────────────────────┘
                             │ manual save or policy-triggered extract
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Memory Record (canonical, scoped, governed)                        │
│  → Fact, Preference, Decision, Pattern, Research, Instruction       │
│  → scoped: Conversation / User / Role / Agent / Site / Global       │
│  → governed by Memory Policy                                        │
└────────────────────────────┬────────────────────────────────────────┘
                             │ promote_to_knowledge (explicit or auto)
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Knowledge Source (indexed, searchable)                             │
│  → sqlite_fts | sqlite_vec | chroma | future: pg_vector...          │
│  → used by agents via mandatory/optional knowledge linking          │
└─────────────────────────────────────────────────────────────────────┘
```

**Key principle:** Memory Record does not know about backends. It targets a Knowledge Source. The Knowledge Source owns the backend type. This means new backends require zero changes to memory tools or Memory Policy.

### 4.2 Memory Record scopes

| Scope | Who can write | Who can read | scope_key value |
|-------|--------------|--------------|-----------------|
| Conversation | Any user (in that conversation) | Same conversation only | conversation docname |
| User | That user only | That user only | frappe.session.user |
| Role | Managers only | Users with that role + visibility="Shared with Role" | role name |
| Agent | Managers only (or agent if allowed by policy) | Agent with matching name | agent docname |
| Site | Managers only | Everyone if visibility="Site" | frappe.local.site |
| Global | Managers only | Everyone if visibility="Global" | "global" |

### 4.3 Memory Policy

Memory Policy is the governance and behavior config layer. It sits between Memory Records and agent runtime.

**What it configures (fields exist, enforcement is phased):**

```
Capture:
  capture_mode: Manual | Auto (on_run_end) | Both
  approval_required: bool
  default_status: Draft | Active
  allowed_record_types: [Fact, Preference, ...]

Retrieval:
  inject_mode: None | Append to System Prompt | Tool Available
  max_records: int
  token_budget: int

Write controls:
  allow_agent_write: bool
  allow_user_scope_write: bool
  allow_role_scope_write: bool (manager override)

Projection:
  auto_promote_to_knowledge: bool
  knowledge_source: Link → Knowledge Source
  promotion_min_confidence: float
  promotion_min_importance: float

Lifecycle:
  ttl_days: int
```

Policy resolution at runtime: **Agent Policy → Site Default → built-in safe defaults.**

---

## 5. The learning system

### 5.1 What "learning" means here

An agent "learns" when something worth remembering is extracted from a run or conversation and saved as a Memory Record for future use. This is different from fine-tuning the model. It is structured, auditable, and reversible.

### 5.2 How extraction works (Phase 3)

When a learning trigger fires:
1. The agent run transcript is assembled
2. If `learning_agent` is set on the Memory Policy, that agent is called with the transcript
3. If not, a built-in extraction prompt runs against the same base model
4. Extracted facts/preferences/decisions are saved as Memory Records
5. Default status is `Draft` (if `approval_required`) or `Active` (if not)

### 5.3 Learning triggers

| Trigger | When it fires |
|---------|--------------|
| Manual | Only when explicitly called |
| End of Conversation | When conversation is closed / marked complete |
| Every N Turns | After every N agent turns in the conversation |

### 5.4 Learning agent pattern

A "learning agent" is just a regular HUF Agent with a specialized system prompt. It receives a conversation transcript and returns structured memory records. This means:
- You can use any model for extraction (not necessarily the same as the active agent)
- You can version and iterate the extraction prompt without touching the main agent
- You can inspect what the learning agent produces before it becomes Active

---

## 6. What exists today vs what is planned

### Today (after PR #275 is merged)

| Capability | Status |
|-----------|--------|
| Memory Record DocType (full schema) | ✅ Done |
| Memory Policy DocType (schema + validation) | ✅ Done (config shell, no runtime enforcement) |
| 5 memory tool handlers | ✅ Done |
| Scoped permission enforcement in tools | ✅ Done |
| Memory → Knowledge Input projection | ✅ Done |
| Projection status tracking | ✅ Done (`Projected`, not `Indexed`) |
| Manager-only Desk access | ✅ Done |
| Native tool wiring in Agent Tool Function | ✅ Done |
| Memory Policy enforcement at runtime | ❌ Phase 2 |
| Agent-linked memory policy | ❌ Phase 2 |
| Auto-inject memory into agent context | ❌ Phase 2 |
| Post-run memory extraction | ❌ Phase 3 |
| Learning agent delegation | ❌ Phase 3 |
| Learning profiles (presets) | ❌ Phase 4 |
| Hybrid FTS + vector search for memory | ❌ Phase 5 |

### Not in scope (ever, by design)

- Automatic promotion of all conversation data to memory (too noisy)
- Fine-tuning or model weight updates
- Replacing Frappe permissions with custom auth
- Memory leaking across user/role/site boundaries

---

## 7. Key files and where to look

| What | Where |
|------|-------|
| Memory tool handlers (save/get/search/archive/promote) | `huf/ai/memory_tools.py` |
| Memory Record controller (validation, projection queue) | `huf/huf/doctype/memory_record/memory_record.py` |
| Memory Record schema | `huf/huf/doctype/memory_record/memory_record.json` |
| Memory Policy controller | `huf/huf/doctype/memory_policy/memory_policy.py` |
| Memory Policy schema | `huf/huf/doctype/memory_policy/memory_policy.json` |
| Knowledge backend abstraction | `huf/ai/knowledge/backends/__init__.py` |
| FTS backend | `huf/ai/knowledge/backends/sqlite_fts.py` |
| Vector backend | `huf/ai/knowledge/backends/sqlite_vec_backend.py` |
| ChromaDB backend | `huf/ai/knowledge/backends/chroma_backend.py` |
| Indexing pipeline | `huf/ai/knowledge/indexer.py` |
| Retrieval pipeline | `huf/ai/knowledge/retriever.py` |
| Knowledge Source controller | `huf/huf/doctype/knowledge_source/knowledge_source.py` |
| Phase plan | `docs/memory/phase-plan.md` |
| RFC (architecture decisions) | `docs/SCOPED_MEMORY_KNOWLEDGE_BRIDGE_RFC.md` |

---

## 8. How to contribute

**Adding a new knowledge backend:**
1. Implement `KnowledgeBackend` in `huf/ai/knowledge/backends/`
2. Register in `get_backend()` in `__init__.py`
3. Add option to Knowledge Source `knowledge_type` field
4. Add validation in `knowledge_source.py` if dependencies need checking

**Adding a new memory scope or record type:**
- Scope types: add to `scope_type` Select field in `memory_record.json`, update `can_read()` and `can_write()` in `memory_tools.py`, update scope resolver in `resolved_key()`
- Record types: add to `record_type` Select field in `memory_record.json` (no code changes needed)

**Implementing a new Memory Policy enforcement (Phase 2+):**
- The policy resolver logic will live in `huf/ai/memory_policy_resolver.py` (to be created)
- It should read the agent's linked policy or fall back to site default from Agent Settings
- Hook into `agent_integration.py` before and after agent runs

**Writing a learning agent:**
- Create a regular Agent with a specialized system prompt for memory extraction
- The system prompt should instruct the agent to output structured memory records
- Link it as `learning_agent` in a Memory Policy

---

## 9. Design decisions and their reasons

| Decision | Why |
|---------|-----|
| Memory Record doesn't know about backends | Adding pg_vector shouldn't require touching memory tools |
| Memory Policy is config-shell-first | The schema needs to stabilize before enforcement. Wrong enforcement is worse than no enforcement. |
| Manager-only Desk access to Memory Records | Desk DocPerm can't enforce per-scope visibility rules. Tool-level access is the correct control path for users. |
| Projection status = "Projected" not "Indexed" | "Indexed" implies the knowledge pipeline has completed. It hasn't — Knowledge Input processing is async. "Projected" means we've handed it off. |
| Learning agent is a regular Agent, not special-cased | Reuses the entire Agent infrastructure. Can be versioned, tested, and swapped independently. |
| Draft default for extracted memory | Automatic extraction without human review is a data quality risk. Draft-first is safer. |

---

## 10. Glossary

| Term | Meaning |
|------|---------|
| **Memory Record** | A canonical scoped fact, preference, decision, pattern, or research note. The source of truth for what an agent has learned. |
| **Memory Policy** | Config governing capture, retrieval, injection, and promotion rules for memory records. Linked to an Agent or set site-wide. |
| **Knowledge Source** | A HUF DocType representing an indexed, searchable knowledge store. Has a pluggable backend (FTS, vector, chroma). |
| **Knowledge Input** | A single item (text, file, URL) that gets indexed into a Knowledge Source. |
| **Knowledge Projection** | The act of converting a Memory Record into a Knowledge Input so it becomes searchable. Status = Projected means it has been handed to the Knowledge Input pipeline. |
| **Learning Agent** | A regular HUF Agent configured specifically to read transcripts and extract Memory Records. |
| **Scope** | The boundary within which a Memory Record is valid and visible. (Conversation / User / Role / Agent / Site / Global) |
| **Visibility** | Fine-grained access control within a scope. (Private / Shared with Role / Shared with Agent / Site / Global) |
| **Agno-direction** | Pluggable reader/store architecture for knowledge, inspired by the Agno (phidata) framework. |
| **Hindsight-direction** | Post-run memory extraction pattern with retain/recall/reflect semantics. |
