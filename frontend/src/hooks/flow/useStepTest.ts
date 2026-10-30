import { useCallback, useEffect, useRef, useState } from 'react';
import { getStepTestInfo, testStep, type StepSampleInput, type StepTestInfo, type StepTestResult } from '@/services/flow/stepTestApi';

/** The last result per step, kept while the editor is open so leaving the Test tab (or the step) does not lose it. */
const lastResults = new Map<string, StepTestResult>();
const keyOf = (flowId: string, nodeId: string) => `${flowId}:${nodeId}`;

export function forgetStepResult(flowId: string, nodeId: string) {
  lastResults.delete(keyOf(flowId, nodeId));
}

export type InfoState = 'loading' | 'ready' | 'error';

const messageOf = (error: unknown, fallback: string) => (error instanceof Error && error.message ? error.message : fallback);

/**
 * State of the Test tab for one step: what the step would receive (`info`), the last test (`result`) and whether
 * one is running. `reload` asks the server again (after a save, or when the tab is opened).
 */
export function useStepTest(flowId: string | undefined, nodeId: string, enabled: boolean, refreshKey = 0) {
  const [info, setInfo] = useState<StepTestInfo | null>(null);
  const [infoState, setInfoState] = useState<InfoState>('loading');
  const [infoError, setInfoError] = useState<string | null>(null);
  const [result, setResult] = useState<StepTestResult | null>(() => (flowId ? lastResults.get(keyOf(flowId, nodeId)) ?? null : null));
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const seq = useRef(0);

  const reload = useCallback(async () => {
    if (!flowId || !enabled) return;
    const mine = ++seq.current;
    setInfoState((s) => (s === 'ready' ? s : 'loading'));
    try {
      const next = await getStepTestInfo(flowId, nodeId);
      if (mine !== seq.current) return;
      setInfo(next);
      setInfoError(null);
      setInfoState('ready');
    } catch (error) {
      if (mine !== seq.current) return;
      setInfoError(messageOf(error, 'Could not load the sample data for this step.'));
      setInfoState('error');
    }
  }, [flowId, nodeId, enabled]);

  const store = useCallback(
    (next: StepTestResult | null) => {
      setResult(next);
      if (!flowId) return;
      if (next) lastResults.set(keyOf(flowId, nodeId), next);
      else lastResults.delete(keyOf(flowId, nodeId));
    },
    [flowId, nodeId]
  );

  const run = useCallback(
    async (sample?: StepSampleInput | Record<string, unknown>) => {
      if (!flowId) return null;
      setRunning(true);
      setRunError(null);
      try {
        const next = await testStep(flowId, nodeId, sample);
        store(next);
        return next;
      } catch (error) {
        setRunError(messageOf(error, 'The test could not run. Try again.'));
        return null;
      } finally {
        setRunning(false);
      }
    },
    [flowId, nodeId, store]
  );

  // Asked again whenever the tab is opened (`refreshKey`), so a sample pinned meanwhile shows up.
  useEffect(() => {
    void reload();
  }, [reload, refreshKey]);

  return { info, infoState, infoError, result, setResult: store, running, runError, setRunError, run, reload };
}
