import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';
import type { ExecutionAnalyticsResponse } from '@/types/executionAnalytics.types';

export async function getExecutionAnalytics(): Promise<ExecutionAnalyticsResponse | null> {
  try {
    const result = await call.get('huf.ai.agent_run_analytics_api.get_execution_analytics', { granularity: 'hour' });
    return result.message as ExecutionAnalyticsResponse;
  } catch (error) {
    handleFrappeError(error, 'Error fetching execution analytics');
    return null;
  }
}
