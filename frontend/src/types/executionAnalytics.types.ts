/** The five dimensions `get_execution_analytics` can break down runs by. */
export type AnalyticsDimension = 'agent' | 'provider' | 'model' | 'conversation' | 'run_kind';

export interface ExecutionAnalyticsSummary {
  run_count: number;
  success_count: number;
  failed_count: number;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  cache_creation_tokens: number;
  total_cost: number;
  duration_ms_sum: number;
  duration_count: number;
  success_rate: number | null;
  average_duration_ms: number | null;
  cache_ratio: number | null;
}

export interface ExecutionAnalyticsResponse {
  summary: ExecutionAnalyticsSummary;
  series: Array<ExecutionAnalyticsSummary & { bucket_start: string }>;
  breakdowns: Array<ExecutionAnalyticsSummary & { dimension: string }>;
  /**
   * Per-segment token totals summed across the window. A value is `number | null`,
   * and `null` means "could not be measured" for that segment (at least one
   * contributing rollup row had no data for it) — it is NOT the same as 0 tokens.
   * A consumer that defaults a `null` entry to 0 will silently render wrong
   * percentages/shares. Missing keys simply were never observed.
   */
  composition_totals: Record<string, number | null>;
  metadata: {
    granularity: 'hour' | 'day';
    dimension: AnalyticsDimension;
    /**
     * The entity value the response was scoped to, echoing the `entity` param
     * sent to `get_execution_analytics`. `null`/absent when the response is
     * the unscoped aggregate (the normal AnalyticsPage case) — only present
     * as a real string on an entity drill-down response, where `breakdowns`
     * is always `[]` and `breakdowns_total_count` is always 0.
     */
    entity?: string | null;
    freshness: string | null;
    /**
     * Total number of distinct dimension values found in the window, before the
     * server caps `breakdowns` at the top 10 (by run_count). Use this to render
     * "top 10 of N" rather than assuming `breakdowns.length` is the full count.
     */
    breakdowns_total_count: number;
    /** Only present once rollup data exists; absent on the pre-rollup empty-response stub. */
    from?: string;
    to?: string;
    source?: 'scheduled_rollup';
  };
}
