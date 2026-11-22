import { useEffect, useState } from 'react';
import { listEventAliases, type EventAliasSummary } from '@/services/automationApi';

export type EventAliasLoadState = 'loading' | 'ready' | 'error';

/** Loads Event Aliases once and reports whether the list is loading, ready or failed. */
export function useEventAliases(): { aliases: EventAliasSummary[]; state: EventAliasLoadState } {
  const [aliases, setAliases] = useState<EventAliasSummary[]>([]);
  const [state, setState] = useState<EventAliasLoadState>('loading');

  useEffect(() => {
    let cancelled = false;
    listEventAliases()
      .then((rows) => {
        if (cancelled) return;
        setAliases(rows);
        setState('ready');
      })
      .catch(() => {
        if (!cancelled) setState('error');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { aliases, state };
}
