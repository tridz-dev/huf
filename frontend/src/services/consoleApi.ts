import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

export interface RunAgentSyncParams {
  agent_name: string;
  prompt: string;
  provider?: string;
  model?: string;
}

export interface RunAgentSyncResult {
  success: boolean;
  response?: string;
  agent_run_id?: string;
  error?: string;
}

export async function runAgentSync(params: RunAgentSyncParams): Promise<RunAgentSyncResult> {
  try {
    const result = await call.post('huf.ai.agent_integration.run_agent_sync', {
      agent_name: params.agent_name,
      prompt: params.prompt,
      provider: params.provider || undefined,
      model: params.model || undefined,
    });
    const message = result?.message ?? result;
    return {
      success: message?.success !== false,
      response: message?.response ?? (typeof message === 'string' ? message : JSON.stringify(message)),
      agent_run_id: message?.agent_run_id,
    };
  } catch (error) {
    handleFrappeError(error, 'Error running agent');
    return { success: false, error: 'Error running agent' };
  }
}
