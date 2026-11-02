import { useEffect, useState } from 'react';
import { flowService } from '../../services/flowService';
import type { FlowRunDetail } from '../../services/flowApi';
import { runCanStillChange } from '../../lib/flow-run/runCanStillChange';

/** One flow run's details, refreshed every 2 s while the run can still change. */
export function useFlowRunDetail(runId: string | null) {
    const [run, setRun] = useState<FlowRunDetail | null>(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        async function fetchRun() {
            if (!runId) return;
            setLoading(true);
            try {
                const data = await flowService.getFlowRun(runId);
                if (data) setRun(data);
            } catch (err) {
                console.error(err);
            } finally {
                setLoading(false);
            }
        }
        fetchRun();
    }, [runId]);

    // Same fallback as the run list: refresh while the run is still queued, running or waiting for someone.
    // A waiting step (code review, approval, a reply) is decided elsewhere (the run sheet, the bell, another person),
    // so this copy of the run, which the canvas draws, must keep refreshing or it keeps showing "Waiting" after the run ended.
    const active = runCanStillChange(run?.status);
    useEffect(() => {
        if (!runId || !active) return;
        const timer = setInterval(async () => {
            try {
                const data = await flowService.getFlowRun(runId);
                if (data) setRun(data);
            } catch (err) {
                console.error(err);
            }
        }, 2000);
        return () => clearInterval(timer);
    }, [runId, active]);

    const refreshRun = async () => {
        if (!runId) return;
        const data = await flowService.getFlowRun(runId);
        if (data) setRun(data);
    };

    return { run, loading, setLoading, refreshRun };
}
