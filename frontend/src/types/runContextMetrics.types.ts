export interface SegmentTokens {
  system: number | null;
  tools: number | null;
  knowledge: number | null;
  history: number | null;
  message: number | null;
  /** Not present in historical (pre-instrumentation) segment_tokens snapshots. */
  tool_exchange?: number | null;
}

export interface PrefixBreakpoint {
  marker: string;
  prefix_hash: string;
}

export type PrefixStability = 'stable' | 'changed' | 'unknown' | 'unavailable';

export interface RunContextMetrics {
  cache_read_share: number | null;
  effective_input_multiplier: number | null;
  prefix_stability: PrefixStability;
  counterfactual_savings: number | null;
}

export interface RunContextMetricsResponse {
  segment_tokens: SegmentTokens | null;
  total_tokens: number | null;
  /** Null when the model's context window is unknown; never a guessed default. */
  context_window: number | null;
  prefix_breakpoints: PrefixBreakpoint[];
  cache_skipped_unsupported_model: boolean | null;
  metrics: RunContextMetrics;
}
