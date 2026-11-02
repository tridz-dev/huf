import { useState, useEffect, useRef } from 'react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from './ui/sheet';
import { flowService } from '../services/flowService';
import type { FlowRunSummary } from '../services/flowApi';
import { Loader2, RefreshCw, PlayCircle } from 'lucide-react';
import { Button } from './ui/button';
import { useSiteTimezone } from '@/lib/serverTime';
import { browserZone, describeZone, sameZone } from '@/lib/flow-run/flowTimeZone';
import { isFinishedStatus } from '@/lib/flow-run/story/runStatus';
import { RunHistoryRow } from './flow/run/RunHistoryRow';
import { useUser } from '@/contexts/UserContext';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { useViewport } from '@/lib/ui/responsive';
import { RUN_BUTTON_LABEL } from '@/lib/flow-run/flowRunPayload';

interface FlowRunHistoryProps {
    flowId: string;
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onSelectRun: (runId: string) => void;
    /** Opens the Run dialog (the flow is tried once, nothing is sent). Offered to editors when there is no run yet. */
    onRunTest?: () => void;
}

export function FlowRunHistory({ flowId, open, onOpenChange, onSelectRun, onRunTest }: FlowRunHistoryProps) {
    const siteZone = useSiteTimezone();
    const { canManage } = useFlowPermissions();
    const { isPhone } = useViewport();
    const { user } = useUser();
    const [runs, setRuns] = useState<FlowRunSummary[]>([]);
    const [loading, setLoading] = useState(false);
    const [loadFailed, setLoadFailed] = useState(false);
    // Only the newest request may update the list: a slow, older answer must not put an outdated (or empty) list back.
    const latest = useRef(0);

    const fetchRuns = async (silent = false) => {
        if (!flowId) return;
        const mine = ++latest.current;
        if (!silent) setLoading(true);
        try {
            const data = await flowService.listFlowRuns(flowId);
            if (mine !== latest.current) return;
            setRuns(data || []);
            setLoadFailed(false);
        } catch (err) {
            console.error(err);
            if (mine === latest.current) setLoadFailed(true);
        } finally {
            if (mine === latest.current) setLoading(false);
        }
    };

    useEffect(() => {
        if (open) {
            fetchRuns();
        }
    }, [open, flowId]);

    // Live updates (socket) are not always available. While the sheet is open, poll quietly so runs started elsewhere
    // (schedule, webhook, document events) show up without a manual refresh; faster while a run is unfinished
    // (queued, running or waiting, e.g. for an approval answered elsewhere). Paused while the browser tab is hidden.
    const hasActiveRun = runs.some((r) => !isFinishedStatus(r.status));
    useEffect(() => {
        if (!open) return;
        const tick = () => {
            if (!document.hidden) fetchRuns(true);
        };
        const timer = setInterval(tick, hasActiveRun ? 3000 : 5000);
        document.addEventListener('visibilitychange', tick);
        return () => {
            clearInterval(timer);
            document.removeEventListener('visibilitychange', tick);
        };
    }, [open, flowId, hasActiveRun]);

    return (
        <Sheet open={open} onOpenChange={onOpenChange}>
            <SheetContent side={isPhone ? 'bottom' : 'right'} className="flex w-full max-w-full flex-col gap-0 overflow-hidden p-0 max-sm:h-[92dvh] max-sm:rounded-t-xl sm:w-[min(420px,62vw)] sm:max-w-none" data-testid="flow-run-history">
                <SheetHeader className="shrink-0 border-b border-border bg-background px-6 pb-4 pt-6 pr-12" data-testid="flow-run-history-header">
                    <div className="flex items-center justify-between">
                        <SheetTitle className="flex items-center gap-2">
                            <PlayCircle className="w-5 h-5 text-muted-foreground" />
                            Run history
                        </SheetTitle>
                        <Button variant="ghost" size="icon" data-testid="flow-run-history-refresh" onClick={() => fetchRuns()} disabled={loading} title="Refresh">
                            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                        </Button>
                    </div>
                    <SheetDescription>
                        Recent runs of this flow, newest first. Pick one to see what happened, step by step.
                    </SheetDescription>
                    {siteZone && !sameZone(browserZone(), siteZone) && (
                        <p className="text-meta text-muted-foreground" data-testid="flow-run-history-timezone">Times are in your time zone ({describeZone(browserZone())}), not the site's ({describeZone(siteZone)}).</p>
                    )}
                </SheetHeader>

                <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-6 py-5" data-testid="flow-run-history-body">
                    {loading && runs.length === 0 ? (
                        <div className="flex justify-center p-8">
                            <Loader2 className="animate-spin w-6 h-6 text-muted-foreground" />
                        </div>
                    ) : runs.length === 0 && loadFailed ? (
                        <div className="text-center p-8 text-sm text-muted-foreground bg-muted/30 rounded-lg border border-dashed" data-testid="flow-run-history-error">
                            Could not load the run history. It will try again in a few seconds, or use Refresh.
                        </div>
                    ) : runs.length === 0 ? (
                        <div className="text-center p-8 text-sm text-muted-foreground bg-muted/30 rounded-lg border border-dashed" data-testid="flow-run-history-empty">
                            <p>
                                {canManage
                                    ? 'No runs found for this flow yet. Run a test to try it now, or publish it so its trigger starts it.'
                                    : 'No runs yet. Runs show up here once the flow has been started.'}
                            </p>
                            {canManage && onRunTest && (
                                <Button size="sm" className="mt-4 gap-2" onClick={onRunTest} data-testid="flow-run-history-run-test">
                                    <PlayCircle className="h-4 w-4" aria-hidden /> {RUN_BUTTON_LABEL}
                                </Button>
                            )}
                        </div>
                    ) : (
                        runs.map((run) => (
                            <RunHistoryRow
                                key={run.name}
                                run={run}
                                currentUser={user?.name}
                                onOpen={() => {
                                    onSelectRun(run.name);
                                    onOpenChange(false);
                                }}
                            />
                        ))
                    )}
                </div>
            </SheetContent>
        </Sheet>
    );
}
