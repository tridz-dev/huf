import { useEffect, useState } from 'react';
import { getKnowledgeInputCountsBySource } from '@/services/knowledge/countsApi';
import { getAgentCountsBySource } from '@/services/knowledge/usageApi';
import { EMPTY_COUNTS, foldCounts, type InputCounts } from '@/components/agent/knowledge/sourceHealth';

/** Per-source document counts (grouped on the server) and "used by N agents". */
export function useLibraryStats(refreshKey: unknown) {
  const [counts, setCounts] = useState<Record<string, InputCounts>>({});
  const [agents, setAgents] = useState<Record<string, number>>({});

  useEffect(() => {
    let alive = true;
    getKnowledgeInputCountsBySource()
      .then((rows) => {
        if (!alive) return;
        const grouped: Record<string, Array<{ status: string; count: number }>> = {};
        for (const r of rows) (grouped[r.knowledge_source] ??= []).push(r);
        setCounts(Object.fromEntries(Object.entries(grouped).map(([k, v]) => [k, foldCounts(v)])));
      })
      .catch(() => alive && setCounts({}));
    getAgentCountsBySource()
      .then((r) => alive && setAgents(r))
      .catch(() => alive && setAgents({}));
    return () => {
      alive = false;
    };
  }, [refreshKey]);

  return { countsFor: (name: string) => counts[name] ?? EMPTY_COUNTS, agentsFor: (name: string) => agents[name] ?? 0 };
}
