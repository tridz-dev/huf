import { useCallback, useEffect, useMemo, useState } from 'react';
import { getKnowledgeInputStatusCounts } from '@/services/knowledgeApi';
import type { KnowledgeInputDoc, KnowledgeSourceDoc } from '@/types/knowledge.types';
import { useActiveIngestion } from './import/useIngestionPolling';
import { computeHealth, countFromStatusRows, countInputs, type InputCounts } from './import/ingestionLabels';

/** Document counts, active import and plain-language health for one source. */
export function useKnowledgeOverview(
  knowledgeSource: string,
  source: KnowledgeSourceDoc | null,
  inputs: KnowledgeInputDoc[],
) {
  const [bump, setBump] = useState(0);
  const refresh = useCallback(() => setBump((b) => b + 1), []);
  const { active, latest } = useActiveIngestion(knowledgeSource, bump);

  const [serverCounts, setServerCounts] = useState<InputCounts | null>(null);
  useEffect(() => {
    let alive = true;
    getKnowledgeInputStatusCounts(knowledgeSource)
      .then((rows) => alive && setServerCounts(countFromStatusRows(rows)))
      .catch(() => alive && setServerCounts(null));
    return () => {
      alive = false;
    };
  }, [knowledgeSource, inputs, bump]);

  // The loaded list is capped; prefer exact server-side totals.
  const localCounts = useMemo(() => countInputs(inputs), [inputs]);
  const counts = serverCounts ?? localCounts;
  const health = computeHealth(source, counts, !!active);
  return { counts, health, active, latest, bump, refresh };
}
