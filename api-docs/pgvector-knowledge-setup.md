# PGVector Knowledge Setup

This document covers the operational setup and validation checklist for the HUF Knowledge PGVector backend.

## Backend strategy

PGVector uses the LlamaIndex `PGVectorStore` adapter, matching the existing Chroma backend strategy. HUF remains responsible for:

- Knowledge Source configuration
- embedding provider/model resolution
- chunk metadata conventions
- backend registration
- indexing/rebuild orchestration

LlamaIndex is responsible for PostgreSQL/pgvector vector-store behavior.

## PostgreSQL requirement

The target PostgreSQL database must support the `vector` extension.

The backend attempts to run:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

If the configured database user does not have permission, create the extension manually as a privileged user before indexing:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

## Expected LlamaIndex table

The configured Knowledge Source field `pgvector_table_name` is passed to LlamaIndex. LlamaIndex creates its own table naming convention internally, usually prefixed from the configured table name.

The HUF backend assumes LlamaIndex's default PGVector table naming pattern for stats and delete-count estimation.

## Metadata used by HUF

Each indexed chunk stores metadata including:

- `site_name`
- `knowledge_source`
- `input_id`
- `input_type`
- `chunk_id`
- `source_title`
- `chunk_index`
- `char_start`
- `char_end`

These fields allow source isolation, delete-by-input, and basic statistics.

## End-to-end validation checklist

1. Create a Knowledge Source with `knowledge_type = pgvector`.
2. Configure embedding model and provider.
3. Configure PGVector connection settings.
4. Add a text Knowledge Input.
5. Index the input.
6. Run test search from the Knowledge Source UI/API.
7. Confirm returned chunks are scoped to the same Knowledge Source.
8. Re-index the same input and confirm old chunks are removed before insert.
9. Rebuild the Knowledge Source and confirm retrieval still works.
10. Confirm `total_chunks` and `total_inputs` update after indexing.
11. Delete/reprocess an input and confirm count behavior is stable.

## Known limitations

- Delete counts are count-before-delete estimates because LlamaIndex's delete-by-filter call does not currently return an affected row count.
- `index_size_bytes` is currently reported as `0` until a backend-specific size query is added.
- Hybrid search is not enabled in the UI yet, though the backend keeps a capability flag for future support.
