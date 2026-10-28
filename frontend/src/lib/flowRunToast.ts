import { toast } from '@/lib/toast';

export interface FlowRunResult {
  flow_run_id: string;
  status: string;
}

/**
 * Report what a run actually did. run_flow executes synchronously and returns the final status, so a
 * resolved call does not mean success.
 */
export function reportFlowRun(result: FlowRunResult): void {
  const status = result.status || '';
  const detail = `Run ${result.flow_run_id}`;
  if (status === 'Failed' || status === 'Error') {
    toast.error('The flow ran but failed', { description: `${detail}. Open Runs to see what went wrong.` });
  } else if (status.startsWith('Waiting')) {
    toast.info('The flow is waiting for approval', { description: `${detail}. It continues once someone responds.` });
  } else if (status === 'Completed' || status === 'Success') {
    toast.success('The flow ran successfully', { description: detail });
  } else {
    toast.info(`The flow is ${status ? status.toLowerCase() : 'running'}`, { description: detail });
  }
}
