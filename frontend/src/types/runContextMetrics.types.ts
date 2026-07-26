export interface SegmentTokens {
  system: number | null;
  tools: number | null;
  knowledge: number | null;
  history: number | null;
  message: number | null;
}

export interface PrefixBreakpoint {
  marker: string;
  prefix_hash: string;
}

export type PrefixStability = 'stable' | 'changed' | 'unknown' | 'unavailable';

export interface RunContextMetrics {
  cache_read_share: number | null;
  effective_input_multiplier: number | null;
  wasted_writes_tokens: number | null;
  prefix_stability: PrefixStability;
  counterfactual_savings: number | null;
}

export interface RunContextMetricsResponse {
  segment_tokens: SegmentTokens | null;
  total_tokens: number | null;
  context_window: number;
  prefix_breakpoints: PrefixBreakpoint[];
  cache_skipped_unsupported_model: boolean | null;
  metrics: RunContextMetrics;
}
