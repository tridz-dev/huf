import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';
import type { RunContextMetricsResponse } from '@/types/runContextMetrics.types';

export async function getRunContextMetrics(runName: string): Promise<RunContextMetricsResponse | null> {
  try {
    const result = await call.get('huf.ai.agent_run_context_api.get_run_context_metrics', { run_name: runName });
    return result.message as RunContextMetricsResponse;
  } catch (error) {
    handleFrappeError(error, 'Error fetching run context metrics');
    return null;
  }
}
