import { isVectorKnowledgeType } from '@/data/knowledge';
import type { KnowledgeSourceDoc } from '@/types/knowledge.types';
import type { KnowledgeSourceFormValues } from '../types';

export const CREATE_SOURCE_DEFAULTS: KnowledgeSourceFormValues = {
  source_name: '',
  description: '',
  knowledge_type: 'sqlite_fts',
  scope: 'Site',
  storage_mode: 'Frappe File',
  chunk_size: 512,
  chunk_overlap: 50,
  disabled: false,
  embedding_model: '',
  vector_dimension: 1536,
  embedding_provider: '',
  chroma_mode: 'File',
  chroma_host: 'localhost',
  chroma_port: 8000,
  chroma_ssl: false,
  pgvector_connection_mode: 'External PostgreSQL',
  pgvector_table_name: 'huf_knowledge_vectors',
  pgvector_distance_metric: 'cosine',
  pgvector_index_type: 'hnsw',
  pgvector_host: 'localhost',
  pgvector_port: 5432,
  pgvector_database: '',
  pgvector_user: '',
  pgvector_password: '',
  pgvector_sslmode: 'prefer',
  advanced_config: {},
};

/** Known embedding model output sizes (matched by substring, longest first). */
const KNOWN_DIMENSIONS: Array<[string, number]> = [
  ['text-embedding-3-large', 3072],
  ['text-embedding-3-small', 1536],
  ['text-embedding-ada-002', 1536],
  ['text-embedding-004', 768],
  ['embed-english-v3', 1024],
  ['embed-multilingual-v3', 1024],
  ['all-minilm', 384],
  ['nomic-embed-text', 768],
];

export function dimensionForModel(model: string): number | undefined {
  const m = model.toLowerCase();
  return KNOWN_DIMENSIONS.find(([key]) => m.includes(key))?.[1];
}

export function looksLikeEmbeddingModel(name: string): boolean {
  return /embed/i.test(name);
}

export function isSmartSearch(type: string | undefined): boolean {
  return !!type && isVectorKnowledgeType(type);
}

export function buildCreatePayload(v: KnowledgeSourceFormValues): Partial<KnowledgeSourceDoc> {
  return {
    source_name: v.source_name.trim(),
    description: v.description || '',
    knowledge_type: v.knowledge_type,
    scope: v.scope,
    storage_mode: v.storage_mode as KnowledgeSourceDoc['storage_mode'],
    chunk_size: v.chunk_size,
    chunk_overlap: v.chunk_overlap,
    disabled: 0,
    embedding_model: v.embedding_model || '',
    vector_dimension: v.vector_dimension ?? 1536,
    embedding_provider: v.embedding_provider || '',
    chroma_mode: v.chroma_mode,
    chroma_host: v.chroma_host || '',
    chroma_port: v.chroma_port ?? 8000,
    chroma_ssl: v.chroma_ssl ? 1 : 0,
    pgvector_connection_mode: v.pgvector_connection_mode,
    pgvector_table_name: v.pgvector_table_name || 'huf_knowledge_vectors',
    pgvector_distance_metric: v.pgvector_distance_metric,
    pgvector_index_type: v.pgvector_index_type,
    pgvector_host: v.pgvector_host || '',
    pgvector_port: v.pgvector_port ?? 5432,
    pgvector_database: v.pgvector_database || '',
    pgvector_user: v.pgvector_user || '',
    pgvector_password: v.pgvector_password || '',
    pgvector_sslmode: v.pgvector_sslmode,
    advanced_config: JSON.stringify(v.advanced_config || {}),
  } as Partial<KnowledgeSourceDoc>;
}
