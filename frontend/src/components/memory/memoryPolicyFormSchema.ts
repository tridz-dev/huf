import * as z from 'zod';

export const memoryScopeTypes = [
  'Conversation',
  'User',
  'Role',
  'Agent',
  'Workspace',
  'Site',
  'Global',
] as const;

export const memoryCaptureModes = ['Manual', 'Agent Suggested', 'Automatic'] as const;
export const memoryDefaultStatuses = ['Draft', 'Active'] as const;
export const memoryInjectModes = ['Never', 'Relevant Only', 'Always', 'Tool Only'] as const;

export const memoryPolicyFormSchema = z.object({
  policy_name: z.string().min(1, 'Policy name is required'),
  description: z.string().optional(),
  enabled: z.boolean().default(true),
  agent: z.string().optional(),

  scope_type: z.enum(memoryScopeTypes).default('Agent'),
  scope_key: z.string().optional(),

  capture_mode: z.enum(memoryCaptureModes).default('Manual'),
  learning_agent: z.string().optional(),
  approval_required: z.boolean().default(true),
  default_status: z.enum(memoryDefaultStatuses).default('Draft'),
  allowed_record_types: z.string().optional(),

  inject_mode: z.enum(memoryInjectModes).default('Tool Only'),
  max_records: z.number().int().min(0).default(5),
  token_budget: z.number().int().min(0).default(1000),

  allow_agent_write: z.boolean().default(false),
  allow_user_scope_write: z.boolean().default(true),
  allow_role_scope_write: z.boolean().default(false),
  allow_agent_scope_write: z.boolean().default(true),
  allow_site_scope_write: z.boolean().default(false),

  auto_promote_to_knowledge: z.boolean().default(false),
  knowledge_source: z.string().optional(),
  promotion_min_confidence: z.number().min(0).max(1).default(0.8),
  promotion_min_importance: z.number().min(0).max(1).default(0.6),

  ttl_days: z.number().int().min(0).default(0),
  metadata_json: z.string().optional(),
}).superRefine((values, ctx) => {
  if (values.auto_promote_to_knowledge && !values.knowledge_source?.trim()) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['knowledge_source'],
      message: 'Knowledge Source is required when Auto Promote to Knowledge is enabled',
    });
  }
});

export type MemoryPolicyFormValues = z.infer<typeof memoryPolicyFormSchema>;
