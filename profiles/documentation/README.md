# Documentation Memory Profile

## Overview

The **Documentation Memory** profile enables HUF to capture and maintain structured documentation state from conversations and runs. It goes beyond simple memory capture to support living documentation that can be updated, versioned, and referenced across projects.

## Key Capabilities

### 📄 Document Types Supported

| Type | Purpose | Example Use Cases |
|------|---------|-------------------|
| `requirements` | Feature specifications, user stories | "The auth system must support OAuth2..." |
| `architecture` | System design, component relationships | "Three-layer architecture with..." |
| `decision` | ADR-style decision records | "We chose PostgreSQL over MongoDB..." |
| `api_contract` | API specifications, schemas | "POST /users accepts {...}" |
| `status` | Progress updates, blockers | "70% complete, blocked by..." |
| `codebase_mapping` | File locations, module purposes | "Entry point is src/main.py..." |
| `glossary` | Domain terms and definitions | "HUF: Human-Unified Framework..." |
| `migration_guide` | Version migration steps | "To migrate from v1 to v2..." |
| `deployment_notes` | Deployment procedures | "Deploy requires environment..." |
| `changelog` | Version changes, release notes | "v2.1.0 added support for..." |

### 🔄 Section-Aware Updates

Unlike append-only memory, Documentation Memory supports **targeted updates**:

- **section_id**: Unique identifier for stable reference
- **supersedes**: Links to previous versions
- **is_update flag**: Indicates update vs. new content
- **update_summary**: Brief description of changes

Example flow:
```
1. Create ADR-001 (section_id: adr-001-storage)
2. Later decision updates it → new record with same section_id
3. Old record marked superseded, new record links to it
```

### 📋 Structured Data Extraction

Each document type has type-specific structured fields:

**Decision documents include:**
- `decision_rationale`: Why the decision was made
- `alternatives_considered`: Options evaluated
- `consequences`: Positive, negative, and neutral outcomes

**API contracts include:**
- `request_schema`: Input structure
- `response_schema`: Output structure
- `auth_methods`: Authentication requirements
- `rate_limits`: Throttling policies

## Configuration

### Profile Settings

```json
{
  "profile": "documentation",
  "default_scope_type": "namespace",
  "default_capture_stage": "post_response_async",
  "storage": {
    "enable_fts_index": true,
    "enable_vector_index": true,
    "allow_update_existing": true,
    "allow_merge": true
  }
}
```

### Scope Recommendations

| Scope | Use Case |
|-------|----------|
| `conversation` | Temporary documentation drafts |
| `user` | Personal notes, learning journals |
| `agent` | Agent-specific documentation |
| `namespace` | **Recommended** - Project/team documentation |
| `global` | Shared patterns, company-wide standards |

## Usage Examples

### Creating Architecture Documentation

```
User: "Our system will use a microservices architecture with 
       API Gateway, Auth Service, and User Service."

→ Extracts to:
{
  "document_type": "architecture",
  "title": "System Architecture Overview",
  "component": "system-design",
  "structured_data": {
    "layers": ["api-gateway", "auth-service", "user-service"],
    "interfaces": ["REST API", "gRPC internal"]
  }
}
```

### Capturing a Decision (ADR)

```
User: "We decided to use Redis for caching instead of Memcached 
       because it supports data structures we need."

→ Extracts to:
{
  "document_type": "decision",
  "title": "ADR-003: Redis for Caching Layer",
  "decision_rationale": "Redis supports data structures...",
  "alternatives_considered": ["Memcached", "In-memory"],
  "consequences": {
    "positive": ["Rich data structures", "Persistence option"],
    "negative": ["Higher memory usage"]
  }
}
```

### Updating Existing Documentation

```
User: "Update the API contract for /users - we now support 
       pagination with cursor-based navigation."

→ Extracts to:
{
  "document_type": "api_contract",
  "section_id": "api-users-list",  // Same ID = update
  "is_update": true,
  "update_summary": "Added cursor-based pagination",
  "supersedes": ["mem_abc123"]
}
```

## Integration with Markdown

Documentation Memory supports optional merge into Markdown documents:

```python
# Merge memory records into a single doc
memory.merge_to_markdown(
    section_ids=["adr-001", "adr-002", "adr-003"],
    output_path="/docs/decisions.md",
    template="adr-index"
)
```

## Retrieval

### Injected Context Format

When retrieved for prompt injection:

```
## Relevant Documentation

### [architecture] System Architecture Overview
**Project:** huf-memory-system | **Status:** approved
**Last updated:** 2024-03-18

The memory system uses SQLite as canonical storage with optional 
vector indexing for semantic search...

### [decision] ADR-001: Storage Backend Choice
**Status:** approved | **Supersedes:** none

Decision: Use SQLite canonical + optional FTS/vector indexing
Rationale: Best balance of portability and capability...
```

### Search Capabilities

- **Full-text search**: Match content, titles, tags
- **Semantic search**: Find conceptually related docs
- **Filtered search**: By project, component, status, type
- **Cross-reference**: Follow `related_sections` links

## Best Practices

### 1. Use Meaningful Section IDs

Good: `adr-001-storage-backend`, `api-auth-oauth2-flow`
Poor: `doc-123`, `section-abc`

### 2. Maintain Status Accurately

- `draft`: Work in progress
- `review`: Ready for feedback
- `approved`: Accepted and active
- `deprecated`: Replaced by newer docs
- `archived`: Historical reference only

### 3. Link Related Documentation

Always populate `related_sections` to create a knowledge graph:
```json
"related_sections": [
  "adr-001-storage-backend",
  "api-memory-record-create"
]
```

### 4. Tag Consistently

Use a consistent tagging convention:
- Domain: `auth`, `storage`, `api`
- Type: `adr`, `spec`, `guide`
- Status: `critical-path`, `experimental`

## File Structure

```
~/code/huf-memory/profiles/documentation/
├── profile.json           # Profile definition and schema
├── capture_prompt.txt     # Extraction prompt for LLM
├── example_records.json   # 2-3 example memory records
└── README.md             # This documentation
```

## References

- PRD Section 17: Documentation-Aware Upgrades
- ADR Template: [Markdown Any Decision Records](https://adr.github.io/madr/)
- API Documentation: [OpenAPI Specification](https://swagger.io/specification/)
