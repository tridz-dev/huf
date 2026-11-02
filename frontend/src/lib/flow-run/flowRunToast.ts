import { toast } from '@/lib/toast';
import { getFlowRunIdentity } from '@/services/flow/flowRunIdentityApi';

export interface FlowRunResult {
  flow_run_id: string;
  status: string;
}

/**
 * Report what a run actually did. run_flow executes synchronously and returns the final status, so a
 * resolved call does not mean success.
 */
export async function reportFlowRun(result: FlowRunResult, mode: 'test' | 'real' = 'real', flowName?: string): Promise<void> {
  const status = result.status || '';
  const identity = await getFlowRunIdentity(result.flow_run_id);
  showFlowRunToast(status, mode, runToastDetail(flowName, identity?.run_number));
}

/** "Order intake · Run #12", "Run #12", "Order intake", or "This run": never the internal run id. */
export function runToastDetail(flowName?: string | null, runNumber?: number | null): string {
  const run = runNumber ? `Run #${runNumber}` : '';
  return [flowName?.trim(), run].filter(Boolean).join(' · ') || 'This run';
}

function showFlowRunToast(status: string, mode: 'test' | 'real', detail: string): void {
  if (mode === 'test' && (status === 'Completed' || status === 'Success')) {
    toast.success('The test run finished', { description: `${detail}. Nothing was sent or changed. Open Runs to see what each step would have done.` });
  } else if (status === 'Failed' || status === 'Error') {
    toast.error('The flow ran but failed', { description: `${detail}. Open Runs to see what went wrong.` });
  } else if (status === 'Waiting Code') {
    toast.info('The flow is running your code', { description: `${detail}. It continues when the code finishes or is approved.` });
  } else if (status.startsWith('Waiting')) {
    toast.info('The flow is waiting for approval', { description: `${detail}. It continues once someone responds.` });
  } else if (status === 'Completed' || status === 'Success') {
    toast.success('The flow ran successfully', { description: detail });
  } else {
    toast.info(`The flow is ${status ? status.toLowerCase() : 'running'}`, { description: detail });
  }
}
