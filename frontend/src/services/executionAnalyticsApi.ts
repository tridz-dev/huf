import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';
import type { ExecutionAnalyticsResponse } from '@/types/executionAnalytics.types';

export interface GetExecutionAnalyticsParams {
  /** ISO start of the analytics window. Omit for the API's own default (last 7 days). */
  fromDate?: string;
  /** Rollup granularity to query. Defaults to 'hour'. */
  granularity?: 'hour' | 'day';
}

export async function getExecutionAnalytics(
  params?: GetExecutionAnalyticsParams
): Promise<ExecutionAnalyticsResponse | null> {
  try {
    const result = await call.get('huf.ai.agent_run_analytics_api.get_execution_analytics', {
      granularity: params?.granularity ?? 'hour',
      ...(params?.fromDate ? { from_date: params.fromDate } : {}),
    });
    return result.message as ExecutionAnalyticsResponse;
  } catch (error) {
    handleFrappeError(error, 'Error fetching execution analytics');
    return null;
  }
}
