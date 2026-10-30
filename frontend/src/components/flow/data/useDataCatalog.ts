import { useCallback, useEffect, useMemo, useState } from 'react';
import { useFlowContext } from '@/contexts/FlowContext';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { getDataCatalog } from '@/services/flow/catalogApi';
import type { RefScope } from '@/lib/flow/flowRefs';
import { buildPickerModel, type PickerModel } from '@/lib/flow-data/model';
import type { DataCatalog } from '@/lib/flow-data/types';

const FRESH_MS = 15_000;
const cache = new Map<string, { at: number; data: DataCatalog | null; pending?: Promise<DataCatalog | null> }>();
const listeners = new Set<() => void>();

const keyOf = (flowId: string, nodeId: string) => `${flowId}:${nodeId}`;

/** Forget what was loaded (after an example is added or a run finishes) so the picker asks again. */
export function invalidateDataCatalog(): void {
  cache.clear();
  listeners.forEach((l) => l());
}

function load(flowId: string, nodeId: string, force: boolean): Promise<DataCatalog | null> {
  const key = keyOf(flowId, nodeId);
  const hit = cache.get(key);
  if (hit?.pending) return hit.pending;
  if (hit && !force && Date.now() - hit.at < FRESH_MS) return Promise.resolve(hit.data);
  const pending = getDataCatalog(flowId, nodeId)
    .then((data) => data, () => null)
    .then((data) => {
      cache.set(key, { at: Date.now(), data });
      listeners.forEach((l) => l());
      return data;
    });
  cache.set(key, { at: hit?.at ?? 0, data: hit?.data ?? null, pending });
  return pending;
}

/**
 * What the "Use data" picker lists for a step: the editor's own graph (so a step added a moment ago is there) plus the
 * server's examples. A failed or slow answer just means fewer examples; the steps still show.
 */
export function useDataCatalog(nodeId: string | undefined, scope: RefScope = 'ancestors'): { model: PickerModel; loading: boolean; refresh: () => void } {
  const { activeFlow } = useFlowContext();
  const { canManage } = useFlowPermissions();
  const flowId = activeFlow?.id;
  const [, bump] = useState(0);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const l = () => bump((n) => n + 1);
    listeners.add(l);
    return () => void listeners.delete(l);
  }, []);

  const refresh = useCallback(() => {
    if (!flowId || !nodeId || !canManage) return;
    setLoading(true);
    void load(flowId, nodeId, true).finally(() => setLoading(false));
  }, [flowId, nodeId, canManage]);

  useEffect(() => {
    if (!flowId || !nodeId || !canManage) return;
    void load(flowId, nodeId, false);
  }, [flowId, nodeId, canManage]);

  const catalog = flowId && nodeId ? cache.get(keyOf(flowId, nodeId))?.data ?? null : null;
  const nodes = activeFlow?.nodes;
  const edges = activeFlow?.edges;
  const model = useMemo(() => buildPickerModel(nodes ?? [], edges ?? [], nodeId, catalog, scope), [nodes, edges, nodeId, catalog, scope]);
  return { model, loading, refresh };
}
