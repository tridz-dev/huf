import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

const NS = 'huf.ai.flow.gateways.samples_api';

export interface GatewaySample {
  found: boolean;
  sample: Record<string, unknown> | null;
  real: boolean;
  received_at?: string | null;
}

/** An invented example message for a chat trigger. Nothing is sent and nothing is recorded. */
export async function getGatewaySample(flowId: string, nodeId: string): Promise<GatewaySample> {
  try {
    const result = await call.post(`${NS}.get_gateway_sample`, { flow_id: flowId, node_id: nodeId });
    return result.message as GatewaySample;
  } catch (error) {
    handleFrappeError(error, 'Could not load a sample message');
  }
}

/** The newest real message that started this flow from the trigger's channel (numbers masked by the server). */
export async function getLastGatewayMessage(flowId: string, nodeId: string): Promise<GatewaySample> {
  try {
    const result = await call.post(`${NS}.get_last_gateway_message`, { flow_id: flowId, node_id: nodeId });
    return result.message as GatewaySample;
  } catch (error) {
    handleFrappeError(error, 'Could not load the last message');
  }
}
