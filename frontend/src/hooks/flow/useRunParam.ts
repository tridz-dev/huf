import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';

/**
 * The open Flow Run lives in the URL (`?run=<id>`), so a reload or a shared link reopens the Run
 * details sheet, back/forward move between runs, and closing the sheet clears it. Other query
 * parameters are left alone.
 */
export function useRunParam(): [string | null, (runId: string | null) => void] {
  const [searchParams, setSearchParams] = useSearchParams();
  const runId = searchParams.get('run');

  const setRunId = useCallback(
    (next: string | null) => {
      setSearchParams((prev) => {
        const sp = new URLSearchParams(prev);
        if (next) sp.set('run', next);
        else sp.delete('run');
        return sp;
      });
    },
    [setSearchParams],
  );

  return [runId, setRunId];
}
