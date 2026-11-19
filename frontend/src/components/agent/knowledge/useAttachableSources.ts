import { useEffect, useState } from 'react';
import { getKnowledgeSources } from '@/services/knowledgeApi';
import { getKnowledgeInputCountsBySource } from '@/services/knowledge/countsApi';
import type { KnowledgeSourceDoc } from '@/types/knowledge.types';
import { EMPTY_COUNTS, computeHealth, foldCounts, type InputCounts, type SourceHealth } from './sourceHealth';

export interface AttachableSource {
  name: string;
  label: string;
  health: SourceHealth;
  counts: InputCounts;
  knowledgeType: string;
}

export function useAttachableSources(open: boolean) {
  const [sources, setSources] = useState<AttachableSource[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    Promise.all([getKnowledgeSources({ limit: 500 }), getKnowledgeInputCountsBySource().catch(() => [])])
      .then(([res, rows]) => {
        if (cancelled) return;
        const grouped = new Map<string, Array<{ status: string; count: number }>>();
        for (const r of rows) {
          grouped.set(r.knowledge_source, [...(grouped.get(r.knowledge_source) ?? []), r]);
        }
        setSources(
          res.items.map((s: KnowledgeSourceDoc) => {
            const counts = grouped.has(s.name) ? foldCounts(grouped.get(s.name)!) : EMPTY_COUNTS;
            return {
              name: s.name,
              label: s.source_name || s.name,
              health: computeHealth(s, counts),
              counts,
              knowledgeType: s.knowledge_type,
            };
          }),
        );
      })
      .catch(() => !cancelled && setSources([]))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [open]);

  return { sources, loading };
}
