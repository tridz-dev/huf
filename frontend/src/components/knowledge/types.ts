import * as z from 'zod';
import { isVectorKnowledgeType } from '@/data/knowledge';

export const knowledgeSourceFormSchema = z.object({
  source_name: z.string().min(1, 'Source name is required'),
  description: z.string().optional(),
  knowledge_type: z.enum(['sqlite_fts', 'sqlite_vec', 'chroma', 'redis'], {
    required_error: 'Knowledge type is required',
  }),
  scope: z.enum(['Site', 'Workspace', 'Agent', 'Global']).default('Site'),
  storage_mode: z.string().default('Frappe File'),
  chunk_size: z.number().int().min(100, 'Minimum chunk size is 100').default(512),
  chunk_overlap: z.number().int().min(0).default(50),
  disabled: z.boolean().default(false),

  // Vector settings (sqlite_vec and chroma)
  embedding_model: z.string().optional(),
  vector_dimension: z.number().int().positive().default(1536).optional(),
  embedding_provider: z.string().optional(),

  // Chroma connection settings (chroma only)
  chroma_mode: z.enum(['File', 'Server']).default('File'),
  chroma_host: z.string().optional(),
  chroma_port: z.number().int().positive().default(8000).optional(),
  chroma_ssl: z.boolean().default(false),

  // Redis connection settings (redis only)
  redis_host: z.string().default('localhost').optional(),
  redis_port: z.number().int().positive().default(6379).optional(),
  redis_username: z.string().optional(),
  redis_password: z.string().optional(),
  redis_index_prefix: z.string().default('huf').optional(),
}).superRefine((values, ctx) => {
  if (isVectorKnowledgeType(values.knowledge_type)) {
    if (!values.embedding_model?.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['embedding_model'],
        message: 'Embedding model is required for vector knowledge sources',
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
        message: 'Chroma host is required in Server mode',
      });
    }
    if (!values.chroma_port || values.chroma_port <= 0) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['chroma_port'],
        message: 'Chroma port must be a positive integer',
      });
    }
  }
  if (values.knowledge_type === 'redis') {
    if (!values.redis_host?.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['redis_host'],
        message: 'Redis host is required',
      });
    }
    if (!values.redis_port || values.redis_port <= 0) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['redis_port'],
        message: 'Redis port must be a positive integer',
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
