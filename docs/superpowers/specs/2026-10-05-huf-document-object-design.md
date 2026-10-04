# HUF Document: first-class documents (Step 2)

Status: DRAFT for review. Not implemented. Step 1 (reading quality) is already on `feat/doc-reading-screen`.

## Intent
Agent-written documents stop being chat artifacts and become durable, searchable workspace objects.
Today a document is an `Artifact` row owned by one conversation: readable only by the conversation owner or a
System Manager, deleted when its message changes, no search, no hierarchy, no sharing.
Success: a document outlives its chat, can be found by keyword, can sit under a parent page, and is readable by
the people it is shared with. Editing, versions, comments, tabs and Word import are out of scope (later steps).

## Decision: a core `HUF Document` DocType, exposed to HUF Tables later
Rejected: building on Huf Data Table now. Its field types have no markdown/rich text, no locked/system table,
search covers 3 fields only, and the DocType is forced to the `HF ` prefix. Extending Data Tables first would
delay documents behind unrelated work. Plan: ship `HUF Document` now; later register it as a locked system table.

## Data model (`HUF Document`)
- `title` (Data, required), `slug`-free; naming: hash.
- `body_markdown` (Long Text), `body_html` (Long Text, read-only cache from the existing renderer, sanitized).
- `parent_document` (Link -> HUF Document; hierarchy; cycle check on save), `sort_order` (Int).
- `summary` (Small Text), `keywords` (Small Text, comma separated; agent-suggested, user-editable).
- `source_artifact` (Link -> Artifact), `source_conversation` (Link -> Agent Conversation), `created_by_agent` (Link -> Agent).
- `owner` standard; sharing via standard Frappe DocShare + role permissions (not System-Manager-only).
- `track_changes` on (history only; no version UI).

## Behaviour
1. "Save to workspace" (new whitelisted API + desktop button on a document card) copies an Artifact into a
   `HUF Document` (idempotent: second save updates the same document via `source_artifact`).
2. Agent tool `save_document` does the same from chat; `create_document` artifacts are unchanged.
3. Render: `get_document_html(name)` reuses `render_document_html` (Step 1 stylesheet) and caches in `body_html`.
4. Search: index title+keywords+body into the existing knowledge FTS5 backend (`ai/knowledge/backends/sqlite_fts.py`)
   via a Knowledge Input projection like Memory Record does (`memory_record.py:124`); API `search_documents(q)`.
   Deferred: v1 ships `list_documents(q=...)` using SQL LIKE over title/keywords/body_markdown; the FTS5 projection is a follow-up.
5. List/tree API: `list_documents(parent=None)` returning children with counts, permission-filtered
   (`permission_query_conditions` + `has_permission` hooks, which Artifact lacks today).
6. Desktop (this step only): a "Documents" entry in the chat rail with a flat search + tree list and the existing
   iframe preview. No editing.

## Out of scope
Notion-style page UI and drag-reordering (Step 3), comments (4), editing/versions/tabs/Word import (5), custom fields.

## Risks / open questions
- Cycle prevention and deleting a parent (proposal: block delete when children exist).
- FTS index freshness when body changes (proposal: re-index in `on_update`).
- Permission default: owner + explicit shares; does the organisation want workspace-wide read by role? (Question for you.)

## Testing
Frappe unit tests for permissions, cycle check, idempotent save, FTS hit; vitest for the desktop list/search.
