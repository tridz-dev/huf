# HUF Memory System - Overview

## Mental Model

The HUF Memory System is like giving your AI agents a long-term memory. Just as humans remember past conversations, learn preferences, and build context over time, agents with memory can:

- **Remember user preferences** across sessions
- **Recall facts** mentioned in previous conversations
- **Build on past discussions** without repeating context
- **Maintain continuity** even when conversations span days or weeks

Think of it as the difference between talking to someone with amnesia (every conversation starts fresh) versus talking to a friend who remembers your history together.

## Key Concepts

### Memory Record

The fundamental unit of the memory system. A Memory Record is a structured piece of information extracted from conversations:

```
┌─────────────────────────────────────────────┐
│  Memory Record                               │
├─────────────────────────────────────────────┤
│  Title: "User prefers dark mode"            │
│  Type: preference                             │
│  Scope: user                                  │
│  Data: {"theme": "dark", "reason": "easier...│
│  Confidence: 0.92                             │
│  Created: 2026-03-28 14:30:00               │
└─────────────────────────────────────────────┘
```

### Memory Profile

A **profile** defines the "shape" of memories for a specific domain. Like a template or schema:

| Profile | Purpose | Example Data |
|---------|---------|--------------|
| Programming | Code-related memories | Code patterns, tech stack, preferences |
| CRM | Customer interactions | Contact info, deal status, next steps |
| Travel | Trip planning | Destinations, dates, preferences |
| Documentation | Knowledge base | API docs, tutorials, concepts |

### Memory Policy

A **policy** controls *when* and *how* memories are captured:

- **Capture Stage**: When to extract (during response, after, at conversation end)
- **Capture Frequency**: How often (every message, every N turns, manual only)
- **Quality Thresholds**: Minimum confidence, schema validation
- **Storage Options**: Raw data, summaries, indexing

### Scope & Visibility

Determines who can see and access memories:

```
Scope Hierarchy (narrow → broad):

conversation → user → agent → namespace → global
    │            │       │         │        │
    │            │       │         │        └─ All agents, all users
    │            │       │         └─ All agents in a group
    │            │       └─ This agent, all users
    │            └─ This user, all this agent's conversations
    └─ Only this conversation
```

## Architecture

### High-Level Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Conversation│────▶│   Capture   │────▶│   Storage   │
│    Context   │     │   Pipeline  │     │   (MariaDB) │
└─────────────┘     └──────┬──────┘     └──────┬──────┘
                           │                     │
                           ▼                     ▼
                    ┌─────────────┐     ┌─────────────┐
                    │    Index    │     │   Search    │
                    │ (FTS/Vector)│◀────│   Retrieval │
                    └─────────────┘     └──────┬──────┘
                                               │
                                               ▼
                                        ┌─────────────┐
                                        │   Inject    │
                                        │   into LLM  │
                                        │   Context   │
                                        └─────────────┘
```

### Core Components

#### 1. Capture Pipeline (`capture.py`)

Handles the extraction of memories from conversation:

- **Producer Modes**:
  - `main_agent`: Agent extracts its own memories
  - `memory_agent`: Dedicated agent for capture
  - `post_run_llm`: Separate LLM call for extraction
  - `rules_only`: Pattern-based, no LLM

- **Capture Stages**:
  - `in_prompt`: During generation (blocking)
  - `post_response_sync`: Immediately after (blocking)
  - `post_response_async`: Background (non-blocking)
  - `conversation_end`: When conversation closes
  - `scheduled`: At specific times

#### 2. Storage Layer (`storage.py`)

Manages persistence and retrieval:

- **Primary Storage**: MariaDB (Frappe DocType)
- **Index Backends**:
  - SQLite FTS5 (full-text search)
  - SQLite + Vector (semantic search)
  - PgVector (PostgreSQL)
  - Custom (bring your own)

#### 3. Retrieval System (`retrieval.py`, `search.py`)

Finds and ranks relevant memories:

- **Search Modes**:
  - Keyword (FTS)
  - Semantic (vector similarity)
  - Hybrid (combined)
  - Filtered (by type, scope, date)

- **Ranking Factors**:
  - Relevance to query
  - Recency
  - Importance score
  - Retrieval frequency

#### 4. Injection System (`injection.py`)

Formats and injects memories into prompts:

- **Retrieval Modes**:
  - `inject`: Automatically include in prompt
  - `tool_only`: Agent must request via tool
  - `hybrid`: Both automatic and on-demand

- **Context Budgeting**:
  - Max items to inject
  - Max tokens for memories
  - Priority-based selection

## Data Flow

### Memory Creation Flow

```
1. Conversation proceeds normally
        │
        ▼
2. Trigger condition met (frequency, stage)
        │
        ▼
3. Capture executed (by owner/mode)
        │
        ▼
4. Schema validation (if required)
        │
        ▼
5. Confidence check (if threshold set)
        │
        ▼
6. Storage (MariaDB + optional indexes)
        │
        ▼
7. Indexing (FTS, Vector, or both)
```

### Memory Retrieval Flow

```
1. Agent receives new message
        │
        ▼
2. Search triggered (auto or tool)
        │
        ▼
3. Query constructed (keywords + vector)
        │
        ▼
4. Candidates retrieved (all indexes)
        │
        ▼
5. Results ranked (relevance + factors)
        │
        ▼
6. Top N selected (respecting budget)
        │
        ▼
7. Formatted and injected into context
```

## Memory Types

Each memory has a semantic type indicating its purpose:

| Type | Description | Example |
|------|-------------|---------|
| `profile` | User characteristics | "User is a software engineer" |
| `preference` | User likes/dislikes | "Prefers Python over JavaScript" |
| `fact` | Objective information | "Company was founded in 2020" |
| `plan` | Future actions/intentions | "Will deploy on Friday" |
| `observation` | Noted event | "User seemed frustrated with X" |
| `insight` | Derived conclusion | "User values performance over cost" |
| `domain_object` | Structured entity | Customer record, product spec |
| `session_state` | Temporary context | Current shopping cart contents |

## Configuration Hierarchy

Settings can be defined at multiple levels with precedence:

```
Agent Instance Settings (highest priority)
         │
         ▼
Memory Policy Settings
         │
         ▼
Memory Profile Defaults
         │
         ▼
System Defaults (lowest priority)
```

## Key Files

| File | Purpose |
|------|---------|
| `huf/huf/memory/setup.py` | Installation, seeding, migration hooks |
| `huf/huf/memory/capture.py` | Capture pipeline implementation |
| `huf/huf/memory/storage.py` | Storage and retrieval abstraction |
| `huf/huf/memory/retrieval.py` | Memory injection and formatting |
| `huf/huf/memory/search.py` | Search and ranking logic |
| `huf/huf/memory/indexing.py` | Index management |
| `huf/huf/doctype/memory_record/` | Memory Record DocType |
| `huf/huf/doctype/memory_profile/` | Memory Profile DocType |
| `huf/huf/doctype/memory_policy/` | Memory Policy DocType |

## Next Steps

- [Getting Started](./getting-started.md) - Set up your first memory-enabled agent
- [Profiles](./profiles.md) - Learn about built-in and custom profiles
- [Capture Modes](./capture-modes.md) - Understand capture timing and modes
- [Retrieval](./retrieval.md) - Deep dive into search and injection
- [API Reference](./api-reference.md) - Python and frontend APIs
- [Best Practices](./best-practices.md) - Recommendations for production use