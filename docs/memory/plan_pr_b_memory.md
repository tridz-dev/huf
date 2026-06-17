# PR B — Knowledge & Memory Merge

> **Branch**: `feat/knowledge-memory-merge`
> **Base**: `feat/sidebar-two-level-nav` (PR A)
> **Depends on**:
> - [PR A — Sidebar Restructure](file:///Users/safwan/.gemini/antigravity/brain/89039298-ae5c-48bc-8e29-837b97c04b0e/plan_pr_a_sidebar.md) (inner sidebar architecture)
> - [PR #282](https://github.com/tridz-dev/huf/pull/282) — Scoped Memory Backend (Memory Record/Policy doctypes, extraction pipeline, memory tools APIs)
>
> **Blocks**: Nothing

---

## Goal

Add "Memory" as a sub-page inside the Knowledge inner sidebar (created in PR A). Users can view, search, and archive their personal memories. The Chat UI also shows which memories were injected into agent responses via a `MemoryContextBadge`.

---

## Knowledge Inner Sidebar (After This PR)

```
┌──────────────┬─────────────────────────┐
│ KNOWLEDGE    │                         │
│  📄 Sources  │  [content area]         │
│  🧠 Memory   │  ← NEW                 │
│──────────────│                         │
│ DATA         │                         │
│  🗂️ Tables   │                         │
└──────────────┴─────────────────────────┘
```

One new item in the inner sidebar. No outer sidebar changes.

---

## What's Inside Memory

Memory Records are atomic facts extracted from conversations by the LLM background extraction pipeline (delivered in [PR #282](https://github.com/tridz-dev/huf/pull/282)):

| Field | Example |
|-------|---------|
| `title` | "Prefers dark mode" |
| `summary_text` | "User mentioned they always use dark mode in Frappe apps" |
| `record_type` | Fact / Preference / Instruction / Context / Reflection / ... (11 types) |
| `visibility` | Private / Shared / Global |
| `importance_score` | 7.5 (out of 10) |
| `confidence` | 0.9 |
| `status` | Active / Archived / Superseded |
| `supersedes` | Link to the older memory this one replaced |
| `source_conversation` | Link to the Agent Conversation it came from |

### Record Types

- **Fact** — "User's company is called Acme Corp"
- **Preference** — "User prefers bullet-point answers"
- **Instruction** — "Always use ERPNext terminology, not SAP"
- **Context** — "User is migrating from Tally to ERPNext"
- **Reflection** — Created on contradiction; archives the old memory and links via `supersedes`
- Plus: Research Note, Decision, Extracted Data, State, Summary, Policy Hint, Observation, Insight, Custom

---

## How Scope Works

The backend (PR #282) defines 7 scope levels. The Memory sub-page only shows **the current user's memories**:

| Scope | Meaning | Shown in Memory sub-page? |
|-------|---------|---------------------------|
| **User** | Personal to logged-in user | ✅ Yes — this is what "My Memory" is |
| **Conversation** | Tied to a single chat session | ❌ No (ephemeral) |
| **Agent** | Tied to a specific agent | ❌ No (admin territory) |
| **Role** | Shared across a role | ❌ No (admin territory) |
| **Workspace / Site / Global** | Broader scopes | ❌ No (admin territory) |

The API call filters: `scope_type=User, scope_key=<current_user_email>, status=Active`.

Agent-scoped and Global memories are managed via Frappe Desk or a future admin panel.

---

## Empty State

When a user has zero memory records:

```
┌────────────────────────────────────────────┐
│                                            │
│          🧠                                │
│          No memories yet                   │
│                                            │
│   Your AI agents haven't learned anything  │
│   about you yet. Start a conversation      │
│   with a memory-enabled agent, and facts,  │
│   preferences, and context will appear     │
│   here automatically.                      │
│                                            │
│          [ Start a Chat → ]                │
│                                            │
└────────────────────────────────────────────┘
```

- "Memory" item in the inner sidebar is **always visible**, even when empty. Users should discover the feature.
- The empty state links to `/chat`.
- Once memories exist, replaced by the searchable/filterable card grid.

---

## How Memory ≠ Knowledge (and why they're siblings)

| | Knowledge Sources | Memory Records |
|-|-------------------|----------------|
| **Created by** | Admin uploads docs/files/URLs | LLM extracts from conversations |
| **Content** | Chunked documents (PDFs, text, web) | Atomic facts (1-2 sentences) |
| **Storage** | SQLite FTS / sqlite-vec / Chroma | Frappe DocType rows |
| **Managed by** | Admin in Sources sub-page | End user in Memory sub-page |
| **Injected how** | RAG retrieval (vector/FTS search) | Direct text injection into system prompt |
| **Mutability** | Rebuild index, re-upload | Archive, supersede (immutable reflection) |

### The Knowledge Projection Bridge

The backend already has a one-way bridge: Memory Records can be **promoted to Knowledge Sources** via the `promote_to_knowledge` flag. When a memory reaches sufficient confidence/importance (configurable in Memory Policy), it becomes a `Knowledge Input` document and gets indexed into a Knowledge Source's vector/FTS store.

```
Memory Record --[promote]--> Knowledge Input --[index]--> Knowledge Source
```

This is why Memory belongs inside Knowledge — they're architecturally connected, not just conceptually similar. This PR can surface a "Promote to Knowledge" action on individual memory cards (stretch goal).

---

## Proposed Changes

### Modified Components

#### [MODIFY] `KnowledgeLandingPage.tsx` (from PR A)

Add "Memory" to the inner sidebar items under the KNOWLEDGE section:

```typescript
const sections = [
  {
    label: "Knowledge",
    items: [
      { title: "Sources", icon: FileText, subPage: "sources" },
      { title: "Memory", icon: Brain, subPage: "memory" },  // ← NEW
    ]
  },
  {
    label: "Data",
    items: [
      { title: "Tables", icon: Database, subPage: "tables" },
    ]
  },
]
```

Add conditional rendering for the Memory sub-page content.

#### [MODIFY] [types.ts](file:///Users/safwan/Code/docker/fdocker/development/ainative/apps/huf/frontend/src/components/chat/types.ts)

Already done — `injected_memories?: string[]` added to `MessageType`.

#### [MODIFY] [ChatMessage.tsx](file:///Users/safwan/Code/docker/fdocker/development/ainative/apps/huf/frontend/src/components/chat/ChatMessage.tsx)

Already done — `MemoryContextBadge` renders next to agent name when `injected_memories` is present.

#### [MODIFY] [chatMessageList.mappers.ts](file:///Users/safwan/Code/docker/fdocker/development/ainative/apps/huf/frontend/src/components/chat/chatMessageList.mappers.ts)

Already done — `injected_memories` mapped from socket events to `MessageType`.

#### [MODIFY] [useChatSocket.tsx](file:///Users/safwan/Code/docker/fdocker/development/ainative/apps/huf/frontend/src/hooks/useChatSocket.tsx)

Already done — `injected_memories` added to `NewAgentMessageEvent`.

### Existing Components (No Changes Needed)

These were already built in the current session and work as-is:

| Component | Path | Status |
|-----------|------|--------|
| [MemoryCard.tsx](file:///Users/safwan/Code/docker/fdocker/development/ainative/apps/huf/frontend/src/components/memory/MemoryCard.tsx) | `components/memory/` | ✅ Built |
| [MemoryList.tsx](file:///Users/safwan/Code/docker/fdocker/development/ainative/apps/huf/frontend/src/components/memory/MemoryList.tsx) | `components/memory/` | ✅ Built |
| [MemoryContextBadge.tsx](file:///Users/safwan/Code/docker/fdocker/development/ainative/apps/huf/frontend/src/components/memory/MemoryContextBadge.tsx) | `components/memory/` | ✅ Built |

### New Components

#### [NEW] `MemorySubPage.tsx`

Thin wrapper that renders `MemoryList` inside the inner-sidebar content area. Replaces the deleted `MemoryDashboardPage`. Structure:

```tsx
export function MemorySubPage() {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-medium">Memory</h2>
        <p className="text-sm text-muted-foreground">
          Facts, preferences, and context your AI agents have learned from conversations.
        </p>
      </div>
      <MemoryList />
    </div>
  );
}
```

### Backend APIs Used (from PR #282)

| API | Usage |
|-----|-------|
| `huf.ai.memory_tools.search_memory_records` | Fetch user's active memories |
| `huf.ai.memory_tools.archive_memory_record` | Archive a memory from the card |
| `huf.ai.memory_tools.get_memory_record` | Fetch individual memory (for MemoryContextBadge popover) |
| `huf.ai.memory_tools.trigger_session_extraction` | Frontend session-end trigger (called from Chat, not from Memory page) |

---

## Open Questions

> [!IMPORTANT]
> **Inner sidebar label**: "Memory" (short, matches other labels like "Sources" and "Tables") vs "My Memory" (signals it's personal/user-scoped)?

> [!NOTE]
> **Permission gating**: If a user has `chat.use` but not `agent.use`, should they see the Knowledge inner sidebar at all? They'd need it to access Memory, but Sources and Tables are admin features. Could show only the Memory item and hide Sources/Tables based on capability.

> [!NOTE]
> **Promote to Knowledge action**: Stretch goal — add a button on MemoryCard that calls the promotion API. This makes the Knowledge Projection bridge visible to the user. Could be deferred to a follow-up PR.

> [!NOTE]
> **Filters on Memory page**: The MemoryList currently fetches all active user memories. Could add filters for record_type (Fact/Preference/Instruction/etc.), a search bar, and sort by importance/date. Could be deferred to a follow-up PR.

---

## Verification Plan

### Manual Testing
- Navigate to Knowledge → inner sidebar shows Sources, **Memory**, Tables
- Click Memory → shows memory cards (or empty state if none)
- Archive a memory → card disappears, toast confirms
- Empty state → shows encouraging message with link to Chat
- Chat UI → agent messages with injected memories show the MemoryContextBadge
- Click badge → popover shows which memory records were used
- Sources and Tables sub-pages → unchanged from PR A
- No regressions in existing Knowledge/Data functionality
