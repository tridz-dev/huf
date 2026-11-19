import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ACTIVE_INGESTION_STATUSES,
  getIngestionStatus,
  listIngestions,
  type IngestionStatusResult,
} from '@/services/knowledgeApi';

const FAST_INTERVAL_MS = 2000;
const SLOW_INTERVAL_MS = 5000;
const SLOW_AFTER_MS = 2 * 60 * 1000;
const MAX_CONSECUTIVE_ERRORS = 5;
export const LOST_TRACK_MESSAGE = 'Lost track of this import, refresh to check again';

function isGone(err: unknown): boolean {
  const e = err as { httpStatus?: number; status?: number; exc_type?: string; message?: string } | null;
  const code = e?.httpStatus ?? e?.status;
  if (code === 403 || code === 404) return true;
  const t = `${e?.exc_type ?? ''} ${e?.message ?? ''}`;
  return /PermissionError|DoesNotExistError|\b(403|404)\b/.test(t);
}

export function isActiveIngestion(status?: string | null): boolean {
  return !!status && ACTIVE_INGESTION_STATUSES.includes(status);
}

/**
 * Polls get_ingestion_status every 2s while the ingestion is active (5s after
 * two minutes), and stops on a terminal status. Calls onFinished once when it
 * flips from active to terminal.
 */
export function useIngestionPolling(
  ingestion: string | null,
  onFinished?: (result: IngestionStatusResult) => void,
) {
  const [data, setData] = useState<IngestionStatusResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lost, setLost] = useState(false);
  const failuresRef = useRef(0);
  const finishedRef = useRef(onFinished);
  finishedRef.current = onFinished;

  const refresh = useCallback(async () => {
    if (!ingestion) return null;
    if (failuresRef.current >= MAX_CONSECUTIVE_ERRORS) return null;
    try {
      const next = await getIngestionStatus(ingestion);
      setData(next);
      setError(null);
      failuresRef.current = 0;
      setLost(false);
      return next;
    } catch (err) {
      failuresRef.current += 1;
      if (isGone(err) || failuresRef.current >= MAX_CONSECUTIVE_ERRORS) {
        failuresRef.current = MAX_CONSECUTIVE_ERRORS;
        setLost(true);
      }
      setError(err instanceof Error ? err.message : 'Could not load progress');
      return null;
    }
  }, [ingestion]);

  useEffect(() => {
    setData(null);
    setLost(false);
    failuresRef.current = 0;
    if (!ingestion) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const startedAt = Date.now();

    const tick = async () => {
      const next = await refresh();
      if (cancelled) return;
      if (failuresRef.current >= MAX_CONSECUTIVE_ERRORS) return;
      if (next && !isActiveIngestion(next.ingestion.status)) {
        finishedRef.current?.(next);
        return;
      }
      const delay = Date.now() - startedAt > SLOW_AFTER_MS ? SLOW_INTERVAL_MS : FAST_INTERVAL_MS;
      timer = setTimeout(() => void tick(), delay);
    };
    void tick();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [ingestion, refresh]);

  return { data, error, refresh, lost, lostMessage: lost ? LOST_TRACK_MESSAGE : null };
}

/** Finds the active ingestion for a source (refresh-safe resume); re-checked when `bump` changes. */
export function useActiveIngestion(knowledgeSource: string | undefined, bump: number = 0) {
  const [active, setActive] = useState<string | null>(null);
  const [latest, setLatest] = useState<string | null>(null);

  useEffect(() => {
    if (!knowledgeSource) return;
    let cancelled = false;
    listIngestions(knowledgeSource, 5)
      .then((rows) => {
        if (cancelled) return;
        setActive(rows.find((r) => isActiveIngestion(r.status))?.name ?? null);
        setLatest(rows[0]?.name ?? null);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [knowledgeSource, bump]);

  return { active, latest, setActive, setLatest };
}
