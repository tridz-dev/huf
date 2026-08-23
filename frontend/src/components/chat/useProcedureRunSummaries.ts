import { useEffect, useRef, useState } from 'react';
import { getProcedureRunSummary, type ProcedureRunSummary } from '@/services/agentProcedureRunApi';

/**
 * Fetches `ProcedureRunSummary` (pinned procedure name + version, step
 * count, duration) for each distinct `Agent Procedure Run` id referenced by
 * a message's tool calls, so `ProcedureRunRow` can render the D8 collapsed
 * copy: `Ran "<name>" · N steps · <duration>`.
 */
export function useProcedureRunSummaries(procedureRunIds: string[]): Record<string, ProcedureRunSummary> {
  const key = procedureRunIds.slice().sort().join(',');
  const [summaries, setSummaries] = useState<Record<string, ProcedureRunSummary>>({});
  const resolvedKeyRef = useRef<string>('');

  useEffect(() => {
    if (!key || resolvedKeyRef.current === key) return;
    let cancelled = false;

    Promise.all(procedureRunIds.map((id) => getProcedureRunSummary(id))).then((results) => {
      if (cancelled) return;
      resolvedKeyRef.current = key;
      const next: Record<string, ProcedureRunSummary> = {};
      results.forEach((summary) => {
        if (summary) next[summary.id] = summary;
      });
      setSummaries(next);
    });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return summaries;
}
