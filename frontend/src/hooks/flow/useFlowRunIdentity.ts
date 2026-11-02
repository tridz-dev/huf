import { useEffect, useState } from 'react';
import { getFlowRunIdentity, type FlowRunIdentity } from '@/services/flow/flowRunIdentityApi';

/** Number and starter of one run, read once per run id. `null` until known (or when it cannot be read). */
export function useFlowRunIdentity(runId: string | null): FlowRunIdentity | null {
    const [state, setState] = useState<{ id: string; identity: FlowRunIdentity | null } | null>(null);
    useEffect(() => {
        if (!runId) return;
        let cancelled = false;
        void getFlowRunIdentity(runId).then((identity) => {
            if (!cancelled) setState({ id: runId, identity });
        });
        return () => { cancelled = true; };
    }, [runId]);
    return state && state.id === runId ? state.identity : null;
}
