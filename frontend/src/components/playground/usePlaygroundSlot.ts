import { useCallback, useRef, useState } from 'react';
import { toast } from 'sonner';
import { evaluateRun, generatePrompt } from '@/services/consoleApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { executeRun } from './runExecutor';
import { IDLE_SLOT, type PlaygroundConfig, type RunOutcome, type SlotState } from './types';

/**
 * Behavior of one prompt/response slot (the single playground bench, or one
 * compare column): run, auto-evaluate, and draft-prompt generation.
 */
export function usePlaygroundSlot(
  config: PlaygroundConfig,
  onConfigChange: (config: PlaygroundConfig) => void,
  recordRun: (config: PlaygroundConfig, outcome: RunOutcome) => void,
) {
  const [state, setState] = useState<SlotState>(IDLE_SLOT);

  // Refs keep the async run/draft closures free of stale state.
  const configRef = useRef(config);
  configRef.current = config;
  const onConfigChangeRef = useRef(onConfigChange);
  onConfigChangeRef.current = onConfigChange;
  const recordRunRef = useRef(recordRun);
  recordRunRef.current = recordRun;

  const run = useCallback(async () => {
    const current = configRef.current;
    if (!current.prompt.trim()) {
      toast.error('Prompt is required');
      return;
    }
    if (!current.provider || !current.model) {
      toast.error('Provider and model are required');
      return;
    }

    setState((prev) => ({ ...prev, running: true, result: null, evaluation: null }));

    let outcome: RunOutcome;
    try {
      outcome = await executeRun(current);
    } catch (error) {
      outcome = { success: false, error: getFrappeErrorMessage(error) };
    }

    setState((prev) => ({ ...prev, running: false, result: outcome }));
    recordRunRef.current(current, outcome);

    // Evaluation runs automatically whenever criteria are set.
    const criteria = current.evaluationCriteria.trim();
    if (outcome.response && criteria) {
      setState((prev) => ({ ...prev, evaluating: true }));
      try {
        const evaluation = await evaluateRun({
          response: outcome.response,
          criteria,
          provider: current.provider || undefined,
          model: current.model || undefined,
        });
        setState((prev) => ({ ...prev, evaluating: false, evaluation }));
      } catch {
        // The service already surfaces the error toast.
        setState((prev) => ({ ...prev, evaluating: false }));
      }
    }
  }, []);

  const draft = useCallback(async () => {
    const current = configRef.current;
    const description = current.prompt.trim();
    if (!description) {
      toast.info('Describe the prompt you want in the field, then use Draft prompt.');
      return;
    }
    if (!window.confirm('Replace the current prompt with a generated draft?')) {
      return;
    }
    setState((prev) => ({ ...prev, generating: true }));
    try {
      const generated = await generatePrompt({ description });
      onConfigChangeRef.current({ ...configRef.current, prompt: generated.prompt });
    } catch {
      // The service already surfaces the error toast.
    } finally {
      setState((prev) => ({ ...prev, generating: false }));
    }
  }, []);

  return { state, run, draft };
}
