import { call } from '@/lib/frappe-sdk';

/** Where a run sits in its flow's history and who started it (for the friendly run title). */
export interface FlowRunIdentity {
    run_number: number;
    started_by: string | null;
    started_by_name: string | null;
}

/** Purely cosmetic: when it fails the title simply has no number or name, so errors are not reported to the user. */
export async function getFlowRunIdentity(flowRunId: string): Promise<FlowRunIdentity | null> {
    try {
        const result = await call.get('huf.ai.flow.run_identity_api.get_flow_run_identity', { flow_run_id: flowRunId });
        return (result.message ?? null) as FlowRunIdentity | null;
    } catch {
        return null;
    }
}
