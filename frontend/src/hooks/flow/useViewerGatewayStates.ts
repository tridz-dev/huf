import { useEffect, useState } from 'react';
import type { Node } from 'reactflow';
import { getGatewayStates } from '@/services/flow/gatewayTriggerApi';
import { isGatewayKindId } from '@/lib/flow-gateway/gatewayWords';
import { onGatewayRegistryChange, peekGatewayRegistry, peekIssueRegistry, setViewerGateways } from '@/lib/flow-gateway/registryStore';
import type { GatewayRegistry } from '@/lib/flow-gateway/gatewayTrigger.types';
import type { FlowNodeData } from '@/types/flow.types';
import { useFlowPermissions } from './useFlowPermissions';

/**
 * For a view-only person: the on/off state of the channels the flow's chat triggers use, so a card of a switched-off
 * channel says "Needs setup" like the editor's. Editors get the full registry elsewhere and ask for nothing here.
 */
export function useViewerGatewayStates(nodes: Array<Node<FlowNodeData>>): GatewayRegistry | null {
  const { canManage } = useFlowPermissions();
  const [issueRegistry, setIssueRegistry] = useState<GatewayRegistry | null>(peekIssueRegistry());
  const names = Array.from(new Set(nodes.flatMap((n) => {
    const cfg = n.data.triggerConfig as { type?: string; gateway?: string } | undefined;
    return n.data.nodeType === 'trigger' && isGatewayKindId(cfg?.type) && cfg?.gateway ? [cfg.gateway] : [];
  }))).sort();
  const key = names.join('\n');

  useEffect(() => onGatewayRegistryChange(() => setIssueRegistry(peekIssueRegistry())), []);
  useEffect(() => {
    if (canManage || peekGatewayRegistry() || !key) return;
    let live = true;
    void getGatewayStates(key.split('\n')).then((rows) => { if (live) setViewerGateways(rows); });
    return () => { live = false; };
  }, [canManage, key]);

  return canManage ? null : issueRegistry;
}
