import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

/** Editors: stop a run that is still waiting for a worker. */
export async function cancelFlowRun(flowRunId: string): Promise<{ flow_run_id: string; status: string }> {
    try {
        const result = await call.post('huf.ai.flow.runs.actions.cancel_flow_run', { flow_run_id: flowRunId });
        return result.message as { flow_run_id: string; status: string };
    } catch (error) {
        handleFrappeError(error, `Error cancelling flow run ${flowRunId}`);
    }
}
