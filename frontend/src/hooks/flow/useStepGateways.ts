import { useEffect, useState } from 'react';
import { embedPolicy } from '@/embed/bridge';
import type { GatewayChoice } from '@/lib/flow-gateway/gatewayTrigger.types';
import { getAppFlowGateways } from '@/services/flow/gatewayTriggerApi';
import { useGatewayRegistry } from './useGatewayRegistry';

type AppAnswer = { restricted: boolean; gateways: GatewayChoice[] } | 'failed' | null;

/**
 * The channels a step's picker offers. In the embedded editor of an app-owned flow the server says which; a limited
 * editor sees only those. Elsewhere it is the registry. `gateways` is null while loading.
 */
export function useStepGateways(flowId: string | undefined, enabled: boolean): { gateways: GatewayChoice[] | null; failed: boolean } {
  const appFlow = embedPolicy() !== null;
  const [answer, setAnswer] = useState<AppAnswer>(null);
  const unrestricted = !appFlow || (typeof answer === 'object' && answer?.restricted === false);
  const { registry, failed } = useGatewayRegistry(enabled && unrestricted);

  useEffect(() => {
    if (!appFlow || !enabled || !flowId) return;
    let current = true;
    getAppFlowGateways(flowId).then(
      (next) => current && setAnswer(next),
      () => current && setAnswer('failed'),
    );
    return () => { current = false; };
  }, [appFlow, enabled, flowId]);

  if (unrestricted) return { gateways: registry?.gateways ?? null, failed };
  if (answer === 'failed') return { gateways: null, failed: true };
  return { gateways: answer?.gateways ?? null, failed: false };
}
