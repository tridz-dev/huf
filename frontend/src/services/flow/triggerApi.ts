import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

/** One document type a "When a document changes" trigger can watch. */
export interface TriggerDoctype {
  name: string;
  /** What people call it ("To-do" for ToDo). */
  label: string;
  group: 'common' | 'yours' | 'apps';
  module: string;
}

/** The most recent real request a flow's webhook received, trimmed and with secrets hidden. */
export interface LastWebhookRequest {
  found: boolean;
  sample: Record<string, unknown> | null;
  received_at: string | null;
}

export async function listTriggerDoctypes(): Promise<TriggerDoctype[]> {
  try {
    const result = await call.post('huf.ai.flow.api.get_trigger_doctypes', {});
    return (result.message as TriggerDoctype[]) ?? [];
  } catch (error) {
    handleFrappeError(error, 'Error fetching document types');
  }
}

export async function getLastWebhookRequest(flowId: string): Promise<LastWebhookRequest> {
  try {
    const result = await call.post('huf.ai.flow.trigger_samples_api.get_last_webhook_request', { flow_id: flowId });
    return result.message as LastWebhookRequest;
  } catch (error) {
    handleFrappeError(error, 'Error loading the last request');
  }
}
