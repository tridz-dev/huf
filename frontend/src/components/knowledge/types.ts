import * as z from 'zod';

export const knowledgeSourceFormSchema = z.object({
  source_name: z.string().min(1, 'Source name is required'),
  description: z.string().optional(),
  knowledge_type: z.enum(['sqlite_fts', 'sqlite_vec'], {
    required_error: 'Knowledge type is required',
  }),
  scope: z.enum(['Site', 'Workspace', 'Agent', 'Global']).default('Site'),
  storage_mode: z.string().default('Frappe File'),
  chunk_size: z.number().int().min(100, 'Minimum chunk size is 100').default(512),
  chunk_overlap: z.number().int().min(0).default(50),
  disabled: z.boolean().default(false),

  // Vector settings (sqlite_vec only)
  embedding_model: z.string().optional(),
  vector_dimension: z.number().int().positive().default(1536).optional(),
  embedding_provider: z.string().optional(),
}).superRefine((values, ctx) => {
  if (values.knowledge_type === 'sqlite_vec') {
    if (!values.embedding_model?.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['embedding_model'],
        message: 'Embedding model is required for SQLite Vec',
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
  if (values.chunk_overlap >= values.chunk_size) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['chunk_overlap'],
      message: 'Chunk overlap must be less than chunk size',
    });
  }
});

export type KnowledgeSourceFormValues = z.infer<typeof knowledgeSourceFormSchema>;
