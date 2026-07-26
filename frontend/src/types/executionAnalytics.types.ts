export interface ExecutionAnalyticsSummary {
  run_count: number;
  success_count: number;
  failed_count: number;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
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
  metadata: { granularity: 'hour' | 'day'; freshness: string | null; source: 'scheduled_rollup' };
}
