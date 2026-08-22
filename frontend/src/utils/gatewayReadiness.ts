import type { GatewayDoc } from '@/services/gatewayApi';

export type ReadinessItem = { id: string; label: string; done: boolean; hint?: string };
export type GatewayReadiness = { ready: boolean; items: ReadinessItem[]; blockingCount: number };

// Blocking items are the ones that must all be done for the gateway to actually work.
// "Receiving traffic" is informational only — a brand-new, correctly-configured gateway
// simply hasn't seen an event yet, so it must never hold up readiness.
const BLOCKING_ITEM_IDS = new Set(['credentials', 'route-target', 'enabled']);

export function getGatewayReadiness(gateway: GatewayDoc): GatewayReadiness {
  const items: ReadinessItem[] = [
    {
      id: 'credentials',
      label: 'Credentials connected',
      done: Boolean(gateway.integration_settings),
      hint: 'Connect credentials for this channel',
    },
    {
      id: 'route-target',
      label: 'Route target set',
      done: Boolean(gateway.default_target_type),
      hint: 'Choose an agent or flow to receive messages',
    },
    {
      id: 'enabled',
      label: 'Gateway enabled',
      done: Boolean(gateway.is_enabled),
      hint: 'Turn the gateway on',
    },
    {
      id: 'receiving-traffic',
      label: 'Receiving messages',
      done: Boolean(gateway.last_event_at),
      hint: 'No messages received yet',
    },
  ];

  if (gateway.last_error) {
    items.push({
      id: 'last-error',
      label: 'Last error',
      done: false,
      hint: gateway.last_error,
    });
  }

  const blockingCount = items.filter((item) => BLOCKING_ITEM_IDS.has(item.id) && !item.done).length;

  return {
    ready: blockingCount === 0,
    items,
    blockingCount,
  };
}
