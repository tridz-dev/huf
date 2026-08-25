import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';
import type { AnalyticsDimension, ExecutionAnalyticsResponse } from '@/types/executionAnalytics.types';

export interface GetExecutionAnalyticsParams {
  /** ISO start of the analytics window. Omit for the API's own default (last 7 days). */
  fromDate?: string;
  /** ISO end of the analytics window. Omit for the API's own default (now). */
  toDate?: string;
  /** Rollup granularity to query. Defaults to 'hour'. */
  granularity?: 'hour' | 'day';
  /** Dimension to break down `breakdowns` by. Defaults to 'provider'. */
  dimension?: AnalyticsDimension;
  /**
   * Scope the response to a single value of `dimension` (e.g. one agent name).
   * When set, the API returns the same top-level shape but `breakdowns` is
   * always `[]` — the caller already knows which entity it wants.
   */
  entity?: string;
}

export async function getExecutionAnalytics(
  params?: GetExecutionAnalyticsParams
): Promise<ExecutionAnalyticsResponse | null> {
  try {
    const result = await call.get('huf.ai.agent_run_analytics_api.get_execution_analytics', {
      granularity: params?.granularity ?? 'hour',
      ...(params?.fromDate ? { from_date: params.fromDate } : {}),
      ...(params?.toDate ? { to_date: params.toDate } : {}),
      ...(params?.dimension ? { dimension: params.dimension } : {}),
      ...(params?.entity ? { entity: params.entity } : {}),
    });
    return result.message as ExecutionAnalyticsResponse;
  } catch (error) {
    handleFrappeError(error, 'Error fetching execution analytics');
    return null;
  }
}
