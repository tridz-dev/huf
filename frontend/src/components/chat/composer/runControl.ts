import { call } from '@/lib/frappe-sdk';

export const CANCELLED_BY_USER = 'Cancelled by user';

export interface CancelRunResult {
  run_id: string;
  status: 'Queued' | 'Started' | 'Success' | 'Failed';
  cancel_requested: boolean;
}

/** Ask the server to cancel a run (POST). Idempotent; resolves with the run's status. */
export async function cancelAgentRun(runId: string): Promise<CancelRunResult> {
  const result = await call.post('huf.ai.run_control.cancel_agent_run', { run_id: runId });
  return (result?.message ?? result) as CancelRunResult;
}
