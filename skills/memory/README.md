# HUF Memory System Skills

This directory contains skills for working with the HUF Agent Memory System.

## Available Skills

| Skill | Description | File |
|-------|-------------|------|
| **capture** | Memory capture modes and triggers | `capture/SKILL.md` |
| **retrieval** | Memory retrieval and prompt injection | `retrieval/SKILL.md` |
| **profiles** | Memory profiles and schemas | `profiles/SKILL.md` |
| **storage** | Storage backends and indexing | `storage/SKILL.md` |
| **tools** | Memory tools for agents | `tools/SKILL.md` |

## Quick Reference

### Capture Modes
- `in_prompt` - During main agent inference
- `post_sync` - Synchronous after response
- `post_async` - Asynchronous background job ⭐
- `specialized_agent` - Dedicated memory agent
- `rules_only` - Deterministic rules

### Triggers
- `every_run`, `every_n_runs`, `every_n_turns`
- `after_tool_call`, `final_response_only`
- `conversation_end`, `idle_timeout`, `manual`, `scheduled`

### Retrieval Modes
- `inject` - Auto-injected into prompt
- `tool_only` - Agent must call tool
- `hybrid` - Top-K injected + tool search ⭐

### Storage Backends
- `none` - Canonical only
- `sqlite_fts` - Full-text search
- `sqlite_vec` - Vector similarity
- `hybrid` - FTS + vector with RRF

## Documentation

- [Memory System Full Documentation](../../docs/MEMORY_SYSTEM.md)
- [PRD](../../PRD.md)
- [Capture & Retrieval Spec](../../tech_specs/CAPTURE_RETRIEVAL.md)
- [Storage Architecture](../../tech_specs/STORAGE_ARCHITECTURE.md)
