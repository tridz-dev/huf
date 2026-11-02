import { redactSample } from '@/lib/flow-trigger/sample';
import type { StepTestResult } from '@/services/flow/stepTestApi';

/** A finished "test" of a trigger that happened in the browser (a request that arrived, a document picked). */
export function triggerResult(output: Record<string, unknown>, summary: string, effect: StepTestResult['effect'] = 'reads'): StepTestResult {
  return {
    status: 'success',
    mode: 'real',
    output,
    output_shortened: false,
    pin_value: redactSample(output),
    duration_ms: 0,
    error: null,
    fix_hint: null,
    tested_at: new Date().toISOString(),
    effect,
    calls_ai: false,
    summary,
    preview: null,
    goes_to: null,
    branch: null,
    warnings: [],
  };
}
