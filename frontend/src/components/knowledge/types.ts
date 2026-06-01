import * as z from 'zod';

const vectorKnowledgeTypes = ['sqlite_vec', 'chroma', 'pgvector'] as const;

export const knowledgeSourceFormSchema = z.object({
  source_name: z.string().min(1, 'Source name is required'),
  description: z.string().optional(),
  knowledge_type: z.enum(['sqlite_fts', 'sqlite_vec', 'chroma', 'pgvector'], {
    required_error: 'Knowledge type is required',
  }),
  scope: z.enum(['Site', 'Workspace', 'Agent', 'Global']).default('Site'),
  storage_mode: z.string().default('Frappe File'),
  chunk_size: z.number().int().min(100, 'Minimum chunk size is 100').default(512),
  chunk_overlap: z.number().int().min(0).default(50),
  disabled: z.boolean().default(false),

  // Vector settings
  embedding_model: z.string().optional(),
  vector_dimension: z.number().int().positive().default(1536).optional(),
  embedding_provider: z.string().optional(),

  // Chroma settings
  chroma_mode: z.enum(['File', 'Server']).default('File').optional(),
  chroma_host: z.string().optional(),
  chroma_port: z.number().int().positive().default(8000).optional(),
  chroma_ssl: z.boolean().default(false).optional(),

  // PGVector settings
  pgvector_connection_mode: z.enum(['External PostgreSQL', 'Site PostgreSQL']).default('External PostgreSQL').optional(),
  pgvector_table_name: z.string().default('huf_knowledge_vectors').optional(),
  pgvector_distance_metric: z.enum(['cosine', 'l2', 'inner_product']).default('cosine').optional(),
  pgvector_host: z.string().optional(),
  pgvector_port: z.number().int().positive().default(5432).optional(),
  pgvector_database: z.string().optional(),
  pgvector_user: z.string().optional(),
  pgvector_password: z.string().optional(),
  pgvector_sslmode: z.enum(['prefer', 'require', 'disable', 'allow', 'verify-ca', 'verify-full']).default('prefer').optional(),
  pgvector_index_type: z.enum(['none', 'hnsw', 'ivfflat']).default('hnsw').optional(),
}).superRefine((values, ctx) => {
  if (vectorKnowledgeTypes.includes(values.knowledge_type as (typeof vectorKnowledgeTypes)[number])) {
    if (!values.embedding_model?.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['embedding_model'],
        message: 'Embedding model is required for vector knowledge types',
      });
    }
    if (!values.vector_dimension || values.vector_dimension <= 0) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['vector_dimension'],
        message: 'Vector dimension must be a positive integer',
      });
    }
  }

  if (values.knowledge_type === 'chroma' && values.chroma_mode === 'Server') {
    if (!values.chroma_host?.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['chroma_host'],
        message: 'Chroma host is required in server mode',
      });
    }
  }

  if (values.knowledge_type === 'pgvector') {
    if (!values.pgvector_table_name?.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['pgvector_table_name'],
        message: 'PGVector table name is required',
      });
    }
    if (values.pgvector_table_name && !/^[A-Za-z_][A-Za-z0-9_]*$/.test(values.pgvector_table_name)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['pgvector_table_name'],
        message: 'Table name must be a valid PostgreSQL identifier',
      });
    }

    if (values.pgvector_connection_mode === 'External PostgreSQL') {
      if (!values.pgvector_host?.trim()) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['pgvector_host'], message: 'Host is required' });
      }
      if (!values.pgvector_database?.trim()) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['pgvector_database'], message: 'Database is required' });
      }
      if (!values.pgvector_user?.trim()) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['pgvector_user'], message: 'User is required' });
      }
    }
  }

  if (values.chunk_overlap >= values.chunk_size) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['chunk_overlap'],
      message: 'Chunk overlap must be less than chunk size',
    });
  }
});

export type KnowledgeSourceFormValues = z.infer<typeof knowledgeSourceFormSchema>;
