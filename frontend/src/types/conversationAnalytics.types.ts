/** The three `Agent Run.run_kind` values a conversation's runs can carry. */
export type ConversationRunKind = 'agent' | 'tool' | 'orchestrator';

/**
 * CUMULATIVE totals summed across every run in the conversation. Kept as a
 * separate object from `current` (the latest-run snapshot) on purpose — a
 * consumer must never render one as a share/percentage of the other; they
 * describe different things (a running sum vs. one point in time).
 */
export interface ConversationAnalyticsTotals {
  cumulative: true;
  run_count: number;
  run_count_by_kind: Record<ConversationRunKind, number>;
  billed_input_tokens: number;
  output_tokens: number;
  cost: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
}

/**
 * SNAPSHOT of the latest run only (highest `sequence`). Never a sum — in
 * particular `peak_context_tokens` describes the size of the context window
 * at that one point in time and must not be added across runs.
 */
export interface ConversationAnalyticsCurrent {
  run: string;
  sequence: number;
  peak_context_tokens: number | null;
  model_context_window: number | null;
  /** `null` whenever `peak_context_tokens` or `model_context_window` is unknown — never defaulted. */
  context_fullness: number | null;
  /**
   * Per-segment token counts. A VALUE of `null` means that segment could not be
   * counted -- which is not the same as zero. Treating it as 0 makes composition
   * percentages silently wrong. The whole object is `null` when nothing was measured.
   */
  segment_tokens: Record<string, number | null> | null;
  tool_exchange_tokens: number | null;
}

export interface ConversationAnalyticsSeriesPoint {
  sequence: number;
  run_kind: ConversationRunKind | null;
  peak_context_tokens: number | null;
  /** Delta vs. the immediately preceding run in the series; `null` if either run lacks `peak_context_tokens`. */
  peak_context_tokens_delta: number | null;
  billed_input_tokens: number;
  output_tokens: number | null;
  cost: number | null;
  status: string | null;
  start_time: string | null;
}

export interface ConversationAnalyticsCache {
  cache_read_tokens: number;
  cache_write_tokens: number;
  uncached_input_tokens: number;
  /** `null` when there is no billed input at all to compute a ratio from. */
  effectiveness: number | null;
}

/** Honest-disclosure counts describing what this response could not measure. */
export interface ConversationAnalyticsMeasurement {
  runs_missing_billed_input: number;
  runs_missing_peak_context: number;
  tool_runs_without_conversation_note: number;
}

export interface ConversationAnalyticsResponse {
  totals: ConversationAnalyticsTotals;
  /** `null` when the conversation has no runs yet. */
  current: ConversationAnalyticsCurrent | null;
  series: ConversationAnalyticsSeriesPoint[];
  cache: ConversationAnalyticsCache;
  measurement: ConversationAnalyticsMeasurement;
}
