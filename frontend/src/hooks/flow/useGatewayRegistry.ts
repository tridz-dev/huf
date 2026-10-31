import { useCallback, useEffect, useState } from 'react';
import { getGatewayRegistry } from '@/services/flow/gatewayTriggerApi';
import { onGatewayRegistryChange, peekGatewayRegistry } from '@/lib/flow-gateway/registryStore';
import type { GatewayRegistry } from '@/lib/flow-gateway/gatewayTrigger.types';

/** The chat trigger registry for a form: loaded once per session, `failed` when the server did not answer (retry with `reload`). */
export function useGatewayRegistry(enabled = true): { registry: GatewayRegistry | null; loading: boolean; failed: boolean; reload: () => void } {
  const [registry, setRegistry] = useState<GatewayRegistry | null>(peekGatewayRegistry());
  const [loading, setLoading] = useState(enabled && !peekGatewayRegistry());
  const [failed, setFailed] = useState(false);

  const load = useCallback((force: boolean) => {
    setLoading(true);
    setFailed(false);
    getGatewayRegistry(force)
      .then((r) => setRegistry(r))
      .catch(() => setFailed(true))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (enabled && !peekGatewayRegistry()) load(false);
    return onGatewayRegistryChange(() => setRegistry(peekGatewayRegistry()));
  }, [load, enabled]);

  return { registry, loading, failed, reload: () => load(true) };
}
