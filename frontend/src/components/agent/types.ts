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
  enable_prompt_caching: z.boolean().optional(),
  context_strategy: z.string().optional(),
  summary_ratio: z.number().optional(),
  history_limit: z.number().optional(),
  max_knowledge_tokens: z.number().optional(),
  max_turns: z.number().optional(),
  enable_conversation_data: z.boolean().optional(),
  autonaming_of_conversation_title: z.boolean().optional(),
});

export type AgentFormValues = z.infer<typeof agentFormSchema>;

