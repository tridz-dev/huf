import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

export interface RunAgentSyncParams {
  agent_name: string;
  prompt: string;
  provider?: string;
  model?: string;
  now?: boolean;
}

export interface RunAgentSyncResult {
  success: boolean;
  response?: string;
  agent_run_id?: string;
  error?: string;
  queued?: boolean;
  status?: string;
  conversation_id?: string;
  session_id?: string;
  sequence?: number;
}

export interface RunPromptSyncParams {
  provider: string;
  model: string;
  prompt: string;
  temperature?: number;
  maxTokens?: number;
  systemPrompt?: string;
}

export interface RunPromptSyncResult {
  success: boolean;
  response?: string;
  provider?: string;
  model?: string;
  latency_ms?: number;
  input_tokens?: number;
  output_tokens?: number;
  cost?: number;
  error?: string;
}

export interface GeneratePromptParams {
  description: string;
  tone?: string;
  audience?: string;
  constraints?: string;
}

export interface GeneratePromptResult {
  prompt: string;
}

export interface EvaluateRunParams {
  response: string;
  criteria: string;
  provider?: string;
  model?: string;
}

export interface EvaluateRunResult {
  passed: boolean;
  score: number;
  reasoning: string;
}

export interface SavePromptTemplateParams {
  prompt_body: string;
  title: string;
  description?: string;
  category?: string;
  visibility?: 'Public' | 'App' | 'Private';
  tags?: string;
}

export interface SavePromptTemplateResult {
  name: string;
  version: number;
}

export async function runAgentSync(params: RunAgentSyncParams): Promise<RunAgentSyncResult> {
  try {
    const payload: Record<string, unknown> = {
      agent_name: params.agent_name,
      prompt: params.prompt,
      provider: params.provider || undefined,
      model: params.model || undefined,
    };
    if (params.now !== undefined) {
      payload.now = params.now;
    }
    const result = await call.post('huf.ai.agent_integration.run_agent_sync', payload);
    const message = result?.message ?? result;
    return {
      success: message?.success !== false,
      response: message?.response ?? (typeof message === 'string' ? message : JSON.stringify(message)),
      agent_run_id: message?.agent_run_id,
      queued: message?.queued,
      status: message?.status,
      conversation_id: message?.conversation_id,
      session_id: message?.session_id,
    };
  } catch (error) {
    handleFrappeError(error, 'Error running agent');
    return { success: false, error: 'Error running agent' };
  }
}

export async function runPromptSync(params: RunPromptSyncParams): Promise<RunPromptSyncResult> {
  try {
    const payload: Record<string, unknown> = {
      provider: params.provider,
      model: params.model,
      prompt: params.prompt,
    };
    if (params.temperature !== undefined) {
      payload.temperature = params.temperature;
    }
    if (params.maxTokens !== undefined) {
      payload.max_tokens = params.maxTokens;
    }
    if (params.systemPrompt !== undefined) {
      payload.system_prompt = params.systemPrompt;
    }
    const result = await call.post('huf.ai.console_api.run_prompt_sync', payload);
    const message = result?.message ?? result;
    return {
      success: message?.success !== false,
      response: message?.response ?? '',
      provider: message?.provider,
      model: message?.model,
      latency_ms: message?.latency_ms,
      input_tokens: message?.input_tokens,
      output_tokens: message?.output_tokens,
      cost: message?.cost,
    };
  } catch (error) {
    handleFrappeError(error, 'Error running prompt');
    return { success: false, error: 'Error running prompt' };
  }
}

export async function generatePrompt(params: GeneratePromptParams): Promise<GeneratePromptResult> {
  try {
    const result = await call.post('huf.ai.console_api.generate_prompt', params);
    return (result?.message ?? result) as GeneratePromptResult;
  } catch (error) {
    handleFrappeError(error, 'Error generating prompt');
    throw error;
  }
}

export async function evaluateRun(params: EvaluateRunParams): Promise<EvaluateRunResult> {
  try {
    const result = await call.post('huf.ai.console_api.evaluate_run', params);
    return (result?.message ?? result) as EvaluateRunResult;
  } catch (error) {
    handleFrappeError(error, 'Error evaluating run');
    throw error;
  }
}

export async function savePromptTemplate(
  params: SavePromptTemplateParams,
): Promise<SavePromptTemplateResult> {
  try {
    const result = await call.post('huf.ai.console_api.save_prompt_template', {
      ...params,
      visibility: params.visibility || 'Private',
    });
    return (result?.message ?? result) as SavePromptTemplateResult;
  } catch (error) {
    handleFrappeError(error, 'Error saving prompt template');
    throw error;
  }
}
