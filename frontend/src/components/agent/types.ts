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
  run_immediately: z.boolean().optional(),
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
  starter_prompts: z.array(
    z.object({
      name: z.string().optional(),
      prompt_text: z.string().min(1, 'Prompt text is required'),
    })
  ).max(3, 'A maximum of 3 starter prompts is allowed.').default([]),
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
  summary_prompt_mode: z.enum(["Local", "Template"]).default("Local"),
  summary_prompt_template: z.string().optional(),
  summary_prompt_version_locked: z.boolean().optional(),
  summary_template_version_at_attach: z.number().optional(),
  summary_prompt: z.string().optional(),
  history_limit: z.number().optional(),
  max_knowledge_tokens: z.number().optional(),
  max_turns: z.number().optional(),
  max_context_chars: z.number().optional(),
  enable_conversation_data: z.boolean().optional(),
  inject_conversation_data: z.boolean().optional(),
  conversation_data_api_permission: z.string().optional(),
  autonaming_of_conversation_title: z.boolean().optional(),
  enable_memory: z.boolean().optional(),
  memory_policy: z.string().optional(),
  enable_memory_search_tool: z.boolean().optional(),
  enable_memory_write_tool: z.boolean().optional(),

  reasoning_mode: z.enum(['Auto', 'Off', 'On']).default('Auto').optional(),
  reasoning_effort: z.enum(['Auto', 'Low', 'Medium', 'High']).default('Auto').optional(),
  reasoning_budget_tokens: z.number().optional(),
  reasoning_summary: z.enum(['None', 'Concise', 'Detailed']).default('None').optional(),

  agent_color: z
    .string()
    .optional()
    .refine(
      (v) => v === undefined || v === '' || /^#[0-9A-Fa-f]{6}$/.test(v),
      { message: 'Use a hex color including #, e.g. #6366F1' },
    ),
  show_tool_execution_details: z.boolean().optional(),

  agent_skill: z.array(
    z.object({
      name: z.string().optional(),
      skill: z.string().min(1, 'Skill is required'),
      mode: z.enum(['Mandatory', 'Optional']).default('Mandatory'),
      auto_load: z.boolean().default(true),
      priority: z.number().default(0),
      description: z.string().optional(),
    })
  ).default([]),

  // Voice
  voice_enabled: z.boolean().optional(),
  voice_engine: z.string().optional(),
  voice_config: z.string().optional(),
  voice_greeting: z.string().optional(),

  // Advanced model overrides
  image_generation_model: z.string().optional(),
  tts_model: z.string().optional(),
  tts_voice: z.string().optional(),
  stt_model: z.string().optional(),

  allow_file_upload: z.boolean().optional(),
  enable_ocr: z.boolean().optional(),
  max_upload_size_mb: z.number().int().nonnegative().optional(),

  allow_code_execution: z.boolean().optional(),
  execution_profile: z.string().optional(),
  execution_shared_dir_limit_mb: z.number().int().nonnegative().optional(),
  allow_ssh: z.boolean().optional(),
  ssh_connections: z.array(z.string()).default([]),

  allow_ask_user: z.boolean().optional(),
  allow_rich_elements: z.boolean().optional(),
  allow_document_artifacts: z.boolean().optional(),
}).superRefine((values, ctx) => {
  if (values.prompt_mode === "Template" && !values.agent_prompt?.trim()) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["agent_prompt"],
      message: 'Select an Agent Prompt when using Template mode',
    });
  }
  if (
    values.context_strategy === "Summarize" &&
    values.summary_prompt_mode === "Template" &&
    !values.summary_prompt_template?.trim()
  ) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["summary_prompt_template"],
      message: 'Select an Agent Summary Prompt when using Template mode for Summary Prompt',
    });
  }
});

export type AgentFormValues = z.infer<typeof agentFormSchema>;
