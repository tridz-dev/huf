# PGVector Knowledge Backend Implementation Plan

_Last updated: 2026-06-01_

This is a documentation-only proposal for adding PostgreSQL/PGVector support to HUF's knowledge layer. It is grounded in the current `develop` implementation of SQLite FTS, SQLite Vec, ChromaDB, the Knowledge Source DocType, and the React knowledge UI.

## 1. Current state on `develop`

HUF currently exposes three backend types in the backend abstraction:

- `sqlite_fts` for keyword search.
- `sqlite_vec` for local vector search using the `sqlite-vec` extension.
- `chroma` for vector search using ChromaDB through the LlamaIndex adapter.

The backend contract is currently defined by `KnowledgeBackend` and returns `ChunkResult` objects. Every backend is expected to implement:

- `initialize(knowledge_source, config)`
- `add_chunks(chunks)`
- `delete_chunks(input_id)`
- `search(query, top_k, filters=None)`
- `clear()`
- `get_stats()`

Backend lookup is currently hardcoded through `get_backend()` in `huf/ai/knowledge/backends/__init__.py`.

## 2. Current ingestion flow

The indexing pipeline is in `huf/ai/knowledge/indexer.py`.

Current flow:

```text
Knowledge Input
  -> extract text
  -> chunk text
  -> build chunk payload
  -> initialize backend from Knowledge Source.knowledge_type
  -> delete old chunks for that input
  -> add chunks
  -> update stats/status
```

The indexer builds backend config from Knowledge Source fields. Today it passes common chunk settings to all backends. For `sqlite_vec` and `chroma`, it also passes:

- `embedding_model`
- `vector_dimension`
- `embedding_provider`

For Chroma, it additionally supports file mode and server mode:

- file mode: private files path under `knowledge/<source>_chroma`
- server mode: `chroma_host`, `chroma_port`, `chroma_ssl`

## 3. Current SQLite Vec implementation

SQLite Vec is local and source-scoped.

Current characteristics:

- One SQLite file per Knowledge Source.
- Stored under the site's private files directory: `private/files/knowledge/<knowledge_source>.sqlite3`.
- Has a `chunks` metadata/content table.
- Has a `chunks_vec` virtual table using `vec0`.
- Uses `FLOAT[dimension]` vectors.
- Generates embeddings during `add_chunks()` using HUF's embedding resolver.
- Deletes chunks by `input_id` by deleting both vector rows and chunk rows.
- Search flow:
  - generate query embedding
  - optionally append SQL filters
  - match against `chunks_vec`
  - join back to `chunks`
  - convert distance into a score using `1 / (1 + distance)`

Important limitation:

- The current filter implementation appends `c.<key> = ?`, so filters are only safe for real columns unless explicitly validated. Metadata JSON fields are not currently exposed as indexed filter columns.

## 4. Current Chroma implementation

Chroma is implemented through LlamaIndex's `ChromaVectorStore`.

Current characteristics:

- Supports local persistent mode and remote server mode.
- Uses a collection per Knowledge Source by default: `huf_<frappe.scrub(knowledge_source)>`.
- Generates embeddings through HUF's embedding resolver before adding documents.
- Stores standard metadata:
  - `input_id`
  - `input_type`
  - `chunk_id`
  - `source_title`
  - `chunk_index`
  - `knowledge_source`
  - extracted metadata
- Supports exact metadata filtering through LlamaIndex `MetadataFilters` and `ExactMatchFilter`.
- Deletes chunks by finding collection IDs where `input_id` matches, then deleting those IDs.
- Provides basic stats and health checks.

Chroma is a useful reference for PGVector because it already demonstrates:

- external vector backend config
- optional dependency handling
- HUF-managed embedding generation
- metadata filters
- backend-specific connection settings

## 5. Current Knowledge Source DocType and UI gaps

The backend DocType currently lists these options:

```text
sqlite_fts
sqlite_vec
chroma
```

Vector settings currently depend on:

```js
['sqlite_vec', 'chroma'].includes(doc.knowledge_type)
```

Chroma-specific fields are shown only when `knowledge_type === 'chroma'`.

Frontend gaps observed:

- `frontend/src/types/knowledge.types.ts` currently defines `KnowledgeType = 'sqlite_fts' | 'sqlite_vec'`, so it is behind the backend DocType because Chroma already exists in the DocType/backend.
- `frontend/src/data/knowledge.ts` currently lists only SQLite FTS and SQLite Vec options.
- `frontend/src/components/knowledge/GeneralTab.tsx` currently shows vector settings only for `sqlite_vec`, not for `chroma` or future `pgvector`.

Before adding PGVector, the frontend should be aligned with current backend reality:

```ts
export type KnowledgeType = 'sqlite_fts' | 'sqlite_vec' | 'chroma' | 'pgvector';
```

And vector settings should be shown for all vector backends:

```ts
const isVectorBackend = ['sqlite_vec', 'chroma', 'pgvector'].includes(watchKnowledgeType);
```

## 6. Why PGVector is useful

PGVector is useful when HUF needs a production-grade vector backend that can combine:

- SQL filtering
- vector similarity ranking
- operational backups
- indexes
- multi-tenant/source-aware tables
- structured metadata columns
- analytics
- future hybrid search with PostgreSQL full-text search

For use cases like travel/hotel recommendation, PGVector is especially useful because the retrieval flow is naturally hybrid:

```text
city / destination / supplier / availability / budget filters
  -> vector ranking for semantic preference fit
  -> agent explanation and recommendation
```

Example user intent:

```text
quiet, comfy hotel with good coffee nearby, not too touristy
```

That should not search all global vectors. It should first filter by city/destination and candidate availability, then rank semantically.

## 7. Recommended PGVector architecture for HUF knowledge

### 7.1 Start with HUF-compatible generic knowledge backend

First implementation should follow the existing backend contract and behave like Chroma/SQLite Vec:

```text
Knowledge Source
  -> one logical PGVector collection/table namespace
  -> chunks with text, metadata, embedding
  -> search returns ChunkResult
```

Recommended backend name:

```text
pgvector
```

Recommended file:

```text
huf/ai/knowledge/backends/pgvector_backend.py
```

Add to backend registry:

```python
"pgvector": "huf.ai.knowledge.backends.pgvector_backend.PGVectorBackend"
```

### 7.2 Avoid one physical table per small source by default

The earlier draft PR approach creates a table name like:

```python
table_name = f"huf_{frappe.scrub(self.knowledge_source)}"
```

That mirrors Chroma's collection-per-source model and is simple. However, for long-term production use, it can create many PostgreSQL tables.

Recommended default:

```text
One shared table per site or configured PGVector database, with knowledge_source as a column.
```

Example logical schema:

```sql
CREATE TABLE huf_knowledge_vectors (
    id BIGSERIAL PRIMARY KEY,
    site_name TEXT NOT NULL,
    knowledge_source TEXT NOT NULL,
    input_id TEXT NOT NULL,
    input_type TEXT NOT NULL,
    chunk_id TEXT NOT NULL UNIQUE,
    source_title TEXT,
    chunk_index INTEGER,
    text TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    embedding VECTOR(1536),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
```

Minimum indexes:

```sql
CREATE INDEX idx_huf_knowledge_vectors_source
ON huf_knowledge_vectors (site_name, knowledge_source);

CREATE INDEX idx_huf_knowledge_vectors_input
ON huf_knowledge_vectors (site_name, knowledge_source, input_id);

CREATE INDEX idx_huf_knowledge_vectors_metadata
ON huf_knowledge_vectors USING GIN (metadata);
```

Vector index, depending on distance strategy:

```sql
CREATE INDEX idx_huf_knowledge_vectors_embedding_hnsw
ON huf_knowledge_vectors
USING hnsw (embedding vector_cosine_ops);
```

For simple MVP, exact scan inside a filtered source is acceptable. Add HNSW/IVFFlat after data volume and latency are measured.

### 7.3 For travel/product recommendation, use structured metadata columns

Generic HUF knowledge can keep metadata in JSONB. But product-specific apps such as GoHoppy/Genie should not rely only on generic JSON metadata for high-cardinality filters.

For hotels, either create a separate app-level PGVector table/tool or extend metadata extraction into structured columns.

Recommended hotel-specific table shape:

```sql
CREATE TABLE hotel_vector_profile (
    id BIGSERIAL PRIMARY KEY,
    hotel_id TEXT NOT NULL,
    supplier TEXT,
    country_code TEXT,
    city_id TEXT NOT NULL,
    neighborhood_id TEXT,
    profile_text TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    embedding VECTOR(1536),
    source_hash TEXT,
    updated_at TIMESTAMPTZ DEFAULT now()
);
```

Indexes:

```sql
CREATE INDEX idx_hotel_vector_city
ON hotel_vector_profile (city_id);

CREATE INDEX idx_hotel_vector_neighborhood
ON hotel_vector_profile (city_id, neighborhood_id);

CREATE INDEX idx_hotel_vector_supplier
ON hotel_vector_profile (supplier);

CREATE INDEX idx_hotel_vector_embedding_hnsw
ON hotel_vector_profile
USING hnsw (embedding vector_cosine_ops);
```

Search pattern:

```sql
SELECT hotel_id, profile_text, metadata,
       1 - (embedding <=> %(query_embedding)s) AS score
FROM hotel_vector_profile
WHERE city_id = %(city_id)s
  AND (%(neighborhood_id)s IS NULL OR neighborhood_id = %(neighborhood_id)s)
ORDER BY embedding <=> %(query_embedding)s
LIMIT %(top_k)s;
```

This is the key advantage over a pure vector store: SQL filters reduce the candidate space before semantic ranking.

## 8. PGVector backend implementation plan

### Phase 1: Minimal backend parity

Goal: PGVector behaves like existing vector backends for generic HUF Knowledge Sources.

Changes:

1. Add optional dependency support:
   - `pgvector`
   - `psycopg` or SQLAlchemy, depending on implementation choice
   - optionally `llama-index-vector-stores-postgres` only if using LlamaIndex adapter
2. Add `PGVectorBackend` implementing `KnowledgeBackend`.
3. Generate embeddings with HUF's existing `get_embedding()` / `get_embeddings()` functions, not implicitly inside LlamaIndex.
4. Store chunks with metadata and embedding.
5. Implement delete by `input_id`.
6. Implement clear by `site_name + knowledge_source`.
7. Implement search with:
   - query embedding
   - source filter
   - optional exact metadata filters
   - vector distance order
8. Return `ChunkResult` consistently.

Recommended approach:

- Prefer direct SQL first for predictable filtering/deletion.
- Avoid hiding too much behavior behind LlamaIndex until filters, deletion, and schema are proven.

### Phase 2: Knowledge Source config and UI

Add `pgvector` to Knowledge Source options.

Add PGVector settings:

- `pgvector_connection_mode`: Site DB / External PostgreSQL
- `pgvector_host`
- `pgvector_port`
- `pgvector_database`
- `pgvector_user`
- `pgvector_password` as Password field
- `pgvector_sslmode`
- `pgvector_table_name`
- `pgvector_distance_metric`: cosine / l2 / inner_product
- `pgvector_index_type`: none / hnsw / ivfflat

For MVP, prefer one of these two choices:

A. External PostgreSQL only:
- simplest when Frappe site DB is MariaDB.
- avoids pretending the current MariaDB site DB can host PGVector.

B. Site DB only when site runs on PostgreSQL:
- useful for future Frappe-on-Postgres installs.
- must detect DB type and fail clearly if site DB is MariaDB.

Given most current Frappe deployments are MariaDB, external PostgreSQL should be treated as the realistic default.

### Phase 3: Backend factory / health support

If the BackendFactory PR is merged, PGVector should register with the factory and expose:

- `health_check()`
- `supports_filters()`
- `supports_hybrid_search()`

Until then, keep compatibility with current hardcoded `get_backend()`.

### Phase 4: Hybrid search

PGVector can later support hybrid retrieval:

- PostgreSQL full-text search over `text`
- vector similarity over `embedding`
- weighted score combination

Example:

```text
final_score = (0.65 * vector_score) + (0.35 * text_score)
```

This should be optional per Knowledge Source.

## 9. Recommended query semantics

Use the same rule across HUF and product tools:

```text
Filter with SQL. Rank with vectors. Explain with the agent.
```

For generic knowledge:

```text
knowledge_source + input_type + metadata filters
  -> vector ranking
```

For hotel recommendation:

```text
city / neighborhood / supplier / available candidates
  -> vector ranking by preference text
  -> refresh price and availability
  -> agent explains selected options
```

Do not use vector DB as the source of truth for:

- payment state
- live availability
- live price
- supplier booking identifiers
- cancellation policy enforcement
- inventory freshness

Use relational/API tools for those.

## 10. Ingestion preparation guidance

Do not embed raw JSON directly.

Prepare a stable, concise `profile_text`.

Generic knowledge example:

```text
Title: Refund Policy
Source: Customer Support Handbook
Content: ...
```

Hotel example:

```text
Hotel Lumiere is a boutique hotel in Le Marais, Paris. It is suitable for couples, guests who prefer walkable neighborhoods, nearby cafes, galleries, bakeries, metro access, and a calm local feel. Rooms are compact but comfortable. It has breakfast, Wi-Fi, and family rooms.
```

Store exact filters separately:

- `city_id`
- `neighborhood_id`
- `supplier`
- `star_rating`
- `price_band`
- `family_friendly`
- `business_friendly`
- `updated_at`

Only re-embed when the profile text changes. Store a `source_hash` to detect this.

## 11. Safety and operational notes

- Do not store PGVector passwords in plain Data fields. Use Frappe Password fields or site config.
- Validate table names; never directly interpolate untrusted names.
- Enforce source/site scoping on every query.
- Add clear errors when optional dependencies are missing.
- Add migration/backfill commands for existing Knowledge Sources.
- Keep PGVector optional so normal HUF install remains lightweight.
- Add tests for:
  - add/search/delete/clear
  - metadata filters
  - missing dependency error
  - dimension mismatch
  - source isolation
  - rebuild flow

## 12. Suggested MVP acceptance criteria

PGVector MVP is acceptable when:

1. `pgvector` appears as a Knowledge Type in backend and frontend.
2. A Knowledge Source can be created with embedding settings and PGVector connection settings.
3. A text/file/url Knowledge Input can be indexed.
4. Re-indexing deletes old chunks for the input before inserting new chunks.
5. Search returns relevant `ChunkResult` values.
6. Search respects `knowledge_source` isolation.
7. Search supports at least exact filters for selected metadata.
8. Clear/rebuild works for one Knowledge Source without affecting others.
9. Missing PGVector dependencies produce actionable errors.
10. PGVector remains optional and does not break SQLite FTS, SQLite Vec, or Chroma installs.

## 13. Suggested implementation order

1. Fix frontend knowledge type parity for Chroma.
2. Add PGVector backend with direct SQL MVP.
3. Add DocType fields and client UI for PGVector connection settings.
4. Add tests for backend behavior.
5. Add bench command or patch to validate/create PGVector schema.
6. Add optional hybrid search after MVP is stable.
7. Add product-level examples for city-filtered travel/hotel retrieval.

## 14. Product guidance for GoHoppy / Genie

Use HUF Knowledge for generic travel policies, destination notes, support documents, and reusable explanation context.

Use app-specific tools for hotel inventory and recommendation:

```text
search_hotels
rank_hotels_by_preference
refresh_hotel_price
get_hotel_details
save_recommendation_snapshot
```

Recommended hotel retrieval flow:

```text
User preference
  -> parse city/neighborhood/date/budget constraints
  -> fetch available candidate hotels from relational DB/API cache
  -> rank candidate hotels semantically using PGVector
  -> refresh live price/availability from supplier API
  -> return shortlist to HUF agent
  -> agent explains why each hotel fits
  -> save shown options as recommendation snapshot
```

This avoids treating hotel inventory as static RAG knowledge while still using vectors where they are strongest: semantic preference matching.
