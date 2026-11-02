import { getLastWebhookRequest } from '@/services/flow/triggerApi';
import { getLastGatewayMessage } from '@/services/flow/gateway/samplesApi';
import { isGatewayKindId } from '../flow-gateway/gatewayWords';
import type { PickerStep } from './model';

export interface LastSample {
  /** A sample to pin on the trigger, or null with a plain `notice`. */
  sample: Record<string, unknown> | null;
  notice: string;
  /** What the person now sees as the example ("message" for chat triggers, "request" for webhooks). */
  noun: 'message' | 'request';
}

/** "Use the last real ..." for a trigger row: chat triggers ask the messages service (numbers masked), webhooks their own endpoint. */
export async function fetchLastSample(flowId: string, step: PickerStep): Promise<LastSample> {
  const kind = (step.node?.data.triggerConfig as { type?: string } | undefined)?.type;
  if (isGatewayKindId(kind)) {
    const last = await getLastGatewayMessage(flowId, step.id);
    const ok = last.found && last.sample;
    return { sample: ok ? last.sample : null, noun: 'message', notice: ok ? '' : 'No message has started this flow yet. Send one to the channel, or use a sample on the Test tab.' };
  }
  const last = await getLastWebhookRequest(flowId);
  const ok = last.found && last.sample;
  return { sample: ok ? (last.sample as Record<string, unknown>) : null, noun: 'request', notice: ok ? '' : 'No request has reached this webhook yet. Send one, then try again.' };
}
