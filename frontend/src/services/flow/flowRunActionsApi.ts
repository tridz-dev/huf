import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

/** Editors: stop a run that is queued or waiting (timer, approval, reply, code). */
export async function cancelFlowRun(flowRunId: string): Promise<{ flow_run_id: string; status: string }> {
    try {
        const result = await call.post('huf.ai.flow.runs.actions.cancel_flow_run', { flow_run_id: flowRunId });
        return result.message as { flow_run_id: string; status: string };
    } catch (error) {
        handleFrappeError(error, `Error cancelling flow run ${flowRunId}`);
    }
}

/** Editors: skip the rest of a timed wait and carry on now. */
export async function continueWaitingRun(flowRunId: string): Promise<{ flow_run_id: string; status: string }> {
    try {
        const result = await call.post('huf.ai.flow.runs.actions.continue_waiting_run', { flow_run_id: flowRunId });
        return result.message as { flow_run_id: string; status: string };
    } catch (error) {
        handleFrappeError(error, `Error continuing flow run ${flowRunId}`);
    }
}

/** Editors: the single-use link that continues a run parked on a resume-mode wait. */
export async function getResumeLink(flowRunId: string): Promise<{ url: string }> {
    try {
        const result = await call.post('huf.ai.flow.runs.actions.get_resume_link', { flow_run_id: flowRunId });
        return result.message as { url: string };
    } catch (error) {
        handleFrappeError(error, `Error getting the resume link of flow run ${flowRunId}`);
    }
}
