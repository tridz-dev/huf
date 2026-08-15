import { useEffect, useState } from 'react';
import { getServiceToolsCached, getCachedServiceToolCount } from '@/services/serviceToolsCache';

interface ServiceToolCountProps {
  service: string;
}

/**
 * Renders "N tools" for an Integration Service card, lazily. Reads a
 * synchronous cache hit immediately (no flicker on re-render); otherwise
 * shows a placeholder until the count resolves.
 */
export function ServiceToolCount({ service }: ServiceToolCountProps) {
  const [count, setCount] = useState<number | undefined>(() => getCachedServiceToolCount(service));

  useEffect(() => {
    if (count !== undefined) return;
    let cancelled = false;
    getServiceToolsCached(service)
      .then((tools) => {
        if (!cancelled) setCount(tools.length);
      })
      .catch(() => {
        if (!cancelled) setCount(0);
      });
    return () => {
      cancelled = true;
    };
  }, [service, count]);

  if (count === undefined) return <span className="text-steel-soft">…</span>;
  return <span>{count} tool{count !== 1 ? 's' : ''}</span>;
}
