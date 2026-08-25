import { useEffect, useRef, useState } from 'react';
import { getProcedureRunsForToolCalls } from '@/services/agentProcedureRunApi';

/**
 * Resolves which `Agent Tool Call` rows (by `tool_call_id`) belong to an
 * `Agent Procedure Run`, so a chat message's tool calls that share a
 * non-null `agent_procedure_run` can collapse into one `ProcedureRunRow`
 * (D8) instead of rendering N individual `Tool` rows.
 *
 * Batches one lookup per distinct set of tool-call ids and caches results
 * for the component's lifetime — the mapping is immutable once a tool call
 * has been assigned to a procedure run.
 */
export function useProcedureRunLookup(toolCallIds: string[]): Record<string, string> {
  const key = toolCallIds.slice().sort().join(',');
  const [map, setMap] = useState<Record<string, string>>({});
  const resolvedKeyRef = useRef<string>('');

  useEffect(() => {
    if (!key || resolvedKeyRef.current === key) return;
    let cancelled = false;

    getProcedureRunsForToolCalls(toolCallIds).then((result) => {
      if (cancelled) return;
      resolvedKeyRef.current = key;
      setMap(result);
    });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return map;
}
