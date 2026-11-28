import { z } from 'zod';
import type { AgentPromptDoc } from '@/services/agentPromptApi';

export const agentPromptFormSchema = z.object({
  title: z.string().min(1, 'Title is required'),
  slug: z.string().optional(),
  description: z.string().optional(),
  is_active: z.boolean().default(true),
  visibility: z.enum(['Public', 'App', 'Private']).default('Private'),
  tags: z.string().optional(),
  prompt_body: z.string().min(1, 'Prompt body is required'),
});

export type AgentPromptFormValues = z.infer<typeof agentPromptFormSchema>;

export function mapDocToFormValues(doc: AgentPromptDoc): AgentPromptFormValues {
  return {
    title: doc.title || '',
    slug: doc.slug || '',
    description: doc.description || '',
    is_active: doc.is_active === 1,
    visibility: doc.visibility || 'Private',
    tags: doc.tags || '',
    prompt_body: doc.prompt_body || '',
  };
}
