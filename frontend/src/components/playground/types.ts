import type { EvaluateRunResult } from '@/services/consoleApi';

export type PlaygroundMode = 'playground' | 'compare';

/**
 * One bench configuration. Temperature / max tokens are kept as raw input
 * strings ('' = unset) so the numeric fields stay controlled without
 * fighting partial input like "0.".
 */
export interface PlaygroundConfig {
  agentName: string;
  provider: string;
  model: string;
  prompt: string;
  evaluationCriteria: string;
  temperature: string;
  maxTokens: string;
}

export function emptyPlaygroundConfig(): PlaygroundConfig {
  return {
    agentName: '',
    provider: '',
    model: '',
    prompt: '',
    evaluationCriteria: '',
    temperature: '',
    maxTokens: '',
  };
}

/** Normalized outcome of a single run (agent or direct). */
export interface RunOutcome {
  success: boolean;
  response?: string;
  error?: string;
  latencyMs?: number;
  inputTokens?: number;
  outputTokens?: number;
  cost?: number;
  model?: string;
  agentRunId?: string;
}

/** Live state of one prompt/response slot. */
export interface SlotState {
  running: boolean;
  generating: boolean;
  evaluating: boolean;
  result: RunOutcome | null;
  evaluation: EvaluateRunResult | null;
}

export const IDLE_SLOT: SlotState = {
  running: false,
  generating: false,
  evaluating: false,
  result: null,
  evaluation: null,
};
