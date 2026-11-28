import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';
import type { GatewayChoice, GatewayRegistry } from '@/lib/flow-gateway/gatewayTrigger.types';
import { peekGatewayRegistry, setGatewayRegistry } from '@/lib/flow-gateway/registryStore';

const ENDPOINT = 'huf.ai.flow.gateways.api.get_gateway_trigger_registry';

let pending: Promise<GatewayRegistry> | null = null;

/** The chat trigger registry: option specs, data fields and the channels this person may use. Cached per session. */
export async function getGatewayRegistry(force = false): Promise<GatewayRegistry> {
  const hit = peekGatewayRegistry();
  if (hit && !force) return hit;
  if (pending) return pending;
  pending = (async () => {
    try {
      const result = await call.post(ENDPOINT, {});
      const registry = result.message as GatewayRegistry;
      setGatewayRegistry(registry);
      return registry;
    } catch (error) {
      handleFrappeError(error, 'Error loading the chat trigger options');
    } finally {
      pending = null;
    }
  })() as Promise<GatewayRegistry>;
  return pending;
}

/** On/off state of the named channels, for people who may read flows but not list channels. */
export async function getGatewayStates(names: string[]): Promise<GatewayChoice[]> {
  try {
    const result = await call.post('huf.ai.flow.gateways.api.get_gateway_states', { names });
    return (result.message ?? []) as GatewayChoice[];
  } catch {
    return [];
  }
}

/**
 * The channels a step of one app-owned flow may use. `restricted` is false when the caller is not limited by the app
 * (then the registry is the list). Never cached: it belongs to one flow.
 */
export async function getAppFlowGateways(flowId: string): Promise<{ restricted: boolean; gateways: GatewayChoice[] }> {
  const result = await call.post('huf.ai.flow.gateways.api.get_app_flow_gateways', { flow_id: flowId });
  return result.message as { restricted: boolean; gateways: GatewayChoice[] };
}
