import * as z from 'zod';

export const agentFormSchema = z.object({
  agent_name: z.string().min(1, 'Agent name is required'),
  provider: z.string().min(1, 'Provider is required'),
  model: z.string().min(1, 'Model is required'),
  temperature: z.number().min(0).max(2),
  top_p: z.number().min(0).max(1),
  disabled: z.boolean(),
  allow_chat: z.boolean(),
  persist_conversation: z.boolean(),
  persist_user_history: z.boolean(),
  enable_multi_run: z.boolean(),
  description: z.string().optional(),
  instructions: z.string(),

  default_plan: z.array(
    z.object({
      name: z.string().optional(),
      step_index: z.number().default(0),
      status: z.enum(["pending", "in_progress", "done", "failed"]).default("pending"),
      instruction: z.string().default(""),
      output_ref: z.string().default("")
    })
  ).default([]),

  prompt_mode: z.enum(["Local", "Template"]).default("Local"),
  agent_prompt: z.string().optional(),
  prompt_version_locked: z.boolean().optional(),
  template_version_at_attach: z.number().optional(),
  allow_guest: z.boolean().default(false),
  allowed_users: z.array(z.string()).default([]),
  allowed_roles: z.array(z.string()).default([]),
  copied_from_prompt: z.string().nullable().optional(),
  enable_prompt_caching: z.boolean().optional(),
  cache_control_type: z.string().optional(),
  cache_system_message: z.boolean().optional(),
  cache_conversation_history: z.boolean().optional(),
  context_strategy: z.string().optional(),
  summary_model: z.string().optional(),
  summary_ratio: z.number().optional(),
  history_limit: z.number().optional(),
  max_knowledge_tokens: z.number().optional(),
  max_turns: z.number().optional(),
  enable_conversation_data: z.boolean().optional(),
  autonaming_of_conversation_title: z.boolean().optional(),

  agent_color: z
    .string()
    .optional()
    .refine(
      (v) => v === undefined || v === '' || /^#[0-9A-Fa-f]{6}$/.test(v),
      { message: 'Use a hex color including #, e.g. #6366F1' },
    ),

  // Advanced model overrides
  image_generation_model: z.string().optional(),
  tts_model: z.string().optional(),
  tts_voice: z.string().optional(),
  stt_model: z.string().optional(),

  // Memory System fields
  enable_memory: z.boolean().default(false),
  memory_policy: z.string().optional(),
  default_memory_scope_type: z.enum(['conversation', 'user', 'agent', 'namespace', 'global']).default('conversation'),
  default_memory_scope_key_template: z.string().optional(),
  memory_retrieval_mode: z.enum(['inject', 'tool_only', 'hybrid']).default('tool_only'),
  memory_in_prompt_budget: z.number().optional(),
  enable_memory_search_tool: z.boolean().default(true),
  enable_memory_write_tool: z.boolean().default(false),
  memory_profile: z.string().optional(),
  memory_agent: z.string().optional(),
  memory_run_order: z.enum(['before_main_response', 'after_main_response', 'background']).default('after_main_response'),
  memory_max_items: z.number().optional(),
  memory_index_backend_default: z.enum(['none', 'sqlite_fts', 'sqlite_vec', 'pgvector', 'custom']).default('sqlite_fts'),
  memory_visibility_default: z.enum(['private', 'shared_with_agent', 'shared_with_namespace', 'global']).default('private'),
}).superRefine((values, ctx) => {
  if (values.prompt_mode === "Template" && !values.agent_prompt?.trim()) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["agent_prompt"],
      message: 'Select an Agent Prompt when using Template mode',
    });
  }
});

export type AgentFormValues = z.infer<typeof agentFormSchema>;
