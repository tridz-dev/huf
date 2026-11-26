import { z } from 'zod';
import type { SkillDoc, SkillTool, SkillKnowledge, SkillPrompt, SkillMcpServer } from '@/types/skill.types';

export const skillFormSchema = z.object({
  skill_name: z.string().optional(),
  title: z.string().min(1, 'Title is required'),
  description: z.string().optional(),
  skill_category: z.string().optional(),
  version: z.string().optional(),
  author: z.string().optional(),
  source_type: z.enum(['Local', 'Git', 'Common Destination', 'App Provided']).default('Local'),
  source_url: z.string().optional(),
  source_path: z.string().optional(),
  source_ref: z.string().optional(),
  provider_app: z.string().optional(),
  status: z.enum(['Draft', 'Active', 'Error', 'Disabled']).default('Active'),
  instructions: z.string().optional(),
  auto_load: z.boolean().default(true),
}).superRefine((v, ctx) => {
  if (v.source_type === 'App Provided' && !v.provider_app?.trim()) {
    ctx.addIssue({ code: 'custom', path: ['provider_app'], message: 'Provider app is required for App Provided skills' });
  }
});

export type SkillFormValues = z.infer<typeof skillFormSchema>;

export function normalizeFlag(value: boolean | number | undefined): 0 | 1 {
  return value === true || value === 1 ? 1 : 0;
}

export function mapDocToFormValues(doc: Partial<SkillDoc>): SkillFormValues {
  return {
    skill_name: doc.skill_name || '',
    title: doc.title || '',
    description: doc.description || '',
    skill_category: doc.skill_category || '',
    version: doc.version || '',
    author: doc.author || '',
    source_type: doc.source_type || 'Local',
    source_url: doc.source_url || '',
    source_path: doc.source_path || '',
    source_ref: doc.source_ref || '',
    provider_app: doc.provider_app || '',
    status: doc.status || 'Active',
    instructions: doc.instructions || '',
    auto_load: doc.auto_load === 1,
  };
}

export function mapFormToPayload(
  values: SkillFormValues,
  tools: SkillTool[],
  knowledge: SkillKnowledge[],
  prompts: SkillPrompt[],
  mcpServers: SkillMcpServer[]
): Partial<SkillDoc> {
  return {
    skill_name: values.skill_name || undefined,
    title: values.title,
    description: values.description || '',
    skill_category: values.skill_category || undefined,
    version: values.version || undefined,
    author: values.author || undefined,
    source_type: values.source_type,
    source_url: values.source_url || undefined,
    source_path: values.source_path || undefined,
    source_ref: values.source_ref || undefined,
    provider_app: values.provider_app || undefined,
    status: values.status,
    instructions: values.instructions || undefined,
    auto_load: normalizeFlag(values.auto_load),
    skill_tools: tools.map((t) => ({
      ...(t.name ? { name: t.name } : {}),
      tool: t.tool,
      description: t.description || undefined,
      required: normalizeFlag(t.required),
    })),
    skill_knowledge: knowledge.map((k) => ({
      ...(k.name ? { name: k.name } : {}),
      knowledge_source: k.knowledge_source,
      mode: k.mode,
      max_chunks: k.max_chunks ?? 5,
      token_budget: k.token_budget ?? 2000,
    })),
    skill_prompts: prompts.map((p) => ({
      ...(p.name ? { name: p.name } : {}),
      prompt: p.prompt,
      usage: p.usage,
    })),
    skill_mcp_servers: mcpServers.map((s) => ({
      ...(s.name ? { name: s.name } : {}),
      mcp_server: s.mcp_server,
      enabled: normalizeFlag(s.enabled),
    })),
  };
}

/** Fields tucked under "Advanced settings"; an error in any of them opens it. */
export const SKILL_ADVANCED_FIELDS: (keyof SkillFormValues)[] = [
  'status',
  'version',
  'author',
  'source_type',
  'provider_app',
  'source_url',
  'source_path',
  'source_ref',
  'auto_load',
];
