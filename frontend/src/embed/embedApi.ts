/** The approval calls the embedded editor makes, always for one flow (the server checks `approve` on it). */
import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';
import type { PendingApproval } from '@/services/flowApi';

export type EmbedApproval = Pick<PendingApproval, 'flow_run_id' | 'title' | 'message' | 'instructions' | 'waiting_since'>;

/** Runs of `flowId` waiting for the current user's approval. Link fields from the server are dropped. */
export async function listFlowApprovals(flowId: string): Promise<EmbedApproval[]> {
  try {
    const result = await call.get('huf.ai.flow.api.get_pending_approvals', { flow_id: flowId });
    const rows = (result.message ?? []) as PendingApproval[];
    return rows
      .filter((row) => row.flow_id === flowId)
      .map(({ flow_run_id, title, message, instructions, waiting_since }) => ({ flow_run_id, title, message, instructions, waiting_since }));
  } catch (error) {
    handleFrappeError(error, 'Error fetching approvals');
  }
}
