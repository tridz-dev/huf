import { useState, useEffect, useRef } from 'react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from './ui/sheet';
import { flowService } from '../services/flowService';
import type { FlowRunSummary } from '../services/flowApi';
import { Loader2, RefreshCw, PlayCircle } from 'lucide-react';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { formatAbsoluteTime, useSiteTimezone } from '@/lib/serverTime';
import { formatTimeAgo } from '@/utils/time';
import { runTimesSentence } from '@/lib/flowTimeZone';

interface FlowRunHistoryProps {
    flowId: string;
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onSelectRun: (runId: string) => void;
}

export function FlowRunHistory({ flowId, open, onOpenChange, onSelectRun }: FlowRunHistoryProps) {
    const siteZone = useSiteTimezone();
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
    const hasActiveRun = runs.some((r) => !['Success', 'Failed', 'Cancelled'].includes(r.status));
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
            <SheetContent className="flex w-[400px] flex-col gap-0 overflow-hidden p-0 sm:w-[500px]" data-testid="flow-run-history">
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
                        Recent runs of this flow, newest first. Select one to see what each step did.
                    </SheetDescription>
                    <p className="text-[11px] text-muted-foreground" data-testid="flow-run-history-timezone">{runTimesSentence(siteZone)}</p>
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
                        <div className="text-center p-8 text-sm text-muted-foreground bg-muted/30 rounded-lg border border-dashed">
                            No runs found for this flow yet. Press Run to try it now, or publish it so its trigger starts it.
                        </div>
                    ) : (
                        runs.map((run) => (
                            <div
                                key={run.name}
                                data-testid={`flow-run-row-${run.name}`}
                                data-run-status={run.status}
                                className="p-3 border rounded-md hover:bg-muted/50 cursor-pointer transition-colors"
                                onClick={() => {
                                    onSelectRun(run.name);
                                    onOpenChange(false);
                                }}
                            >
                                <div className="flex justify-between items-start mb-2">
                                    <div className="font-medium text-sm truncate pr-2" title={run.name}>
                                        {run.name}
                                    </div>
                                    <Badge
                                        variant={
                                            run.status === 'Success' ? 'default' :
                                                run.status === 'Failed' ? 'destructive' : 'secondary'
                                        }
                                    >
                                        {run.status}
                                    </Badge>
                                </div>
                                <div className="text-xs text-muted-foreground flex justify-between items-center">
                                    <span className="truncate max-w-[150px]">Trigger: {run.trigger_type}</span>
                                    {run.started_at && <span title={formatTimeAgo(run.started_at)}>{formatAbsoluteTime(run.started_at)}</span>}
                                </div>
                            </div>
                        ))
                    )}
                </div>
            </SheetContent>
        </Sheet>
    );
}
