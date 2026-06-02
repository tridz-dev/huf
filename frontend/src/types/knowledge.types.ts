export type KnowledgeType = 'sqlite_fts' | 'sqlite_vec' | 'chroma' | 'pgvector';
export type KnowledgeScope = 'Site' | 'Workspace' | 'Agent' | 'Global';
export type KnowledgeSourceStatus = 'Pending' | 'Indexing' | 'Ready' | 'Error' | 'Rebuilding';
export type KnowledgeStorageMode = 'Frappe File';

export type KnowledgeInputType = 'File' | 'Text' | 'URL';
export type KnowledgeInputStatus = 'Pending' | 'Processing' | 'Indexed' | 'Error';

/**
 * Knowledge Source document from Frappe
 * Based on the Knowledge Source doctype schema
 */
export interface KnowledgeSourceDoc {
  // Standard Frappe fields
  name: string;
  owner: string;
  creation: string;
  modified: string;
  modified_by: string;
  docstatus: number;
  idx: number;
  doctype: 'Knowledge Source';

  // Configuration
  source_name: string;
  description?: string | null;
  knowledge_type: KnowledgeType;
  scope: KnowledgeScope;

  // Vector settings
  embedding_model?: string | null;
  vector_dimension?: number | null;
  embedding_provider?: string | null;

  // Chroma settings
  chroma_mode?: 'File' | 'Server' | null;
  chroma_host?: string | null;
  chroma_port?: number | null;
  chroma_ssl?: number | null;

  // PGVector settings
  pgvector_connection_mode?: 'External PostgreSQL' | 'Site PostgreSQL' | null;
  pgvector_table_name?: string | null;
  pgvector_distance_metric?: 'cosine' | 'l2' | 'inner_product' | null;
  pgvector_host?: string | null;
  pgvector_port?: number | null;
  pgvector_database?: string | null;
  pgvector_user?: string | null;
  pgvector_password?: string | null;
  pgvector_sslmode?: 'prefer' | 'require' | 'disable' | 'allow' | 'verify-ca' | 'verify-full' | null;
  pgvector_index_type?: 'none' | 'hnsw' | 'ivfflat' | null;

  // Storage
  storage_mode: KnowledgeStorageMode;
  sqlite_file?: string | null;
  sqlite_file_path?: string | null;

  // Chunking
  chunk_size: number;
  chunk_overlap: number;

  // Status (all read-only)
  status: KnowledgeSourceStatus;
  last_indexed_at?: string | null;
  total_chunks: number;
  total_inputs: number;
  index_size_bytes: number;
  error_message?: string | null;

  disabled: number; // 0 or 1
}

/**
 * Knowledge Input document from Frappe
 * Based on the Knowledge Input doctype schema
 */
export interface KnowledgeInputDoc {
  // Standard Frappe fields
  name: string;
  owner: string;
  creation: string;
  modified: string;
  modified_by: string;
  docstatus: number;
  idx: number;
  doctype: 'Knowledge Input';

  // Core fields
  knowledge_source: string;
  input_type: KnowledgeInputType;

  // Type-specific fields
  file?: string | null;
  file_name?: string | null;
  file_type?: string | null;
  text?: string | null;
  url?: string | null;

  // Status (all read-only)
  status: KnowledgeInputStatus;
  source_hash?: string | null;
  chunks_created: number;
  character_count: number;
  processed_at?: string | null;
  error_message?: string | null;
}
