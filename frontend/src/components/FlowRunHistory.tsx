import { useState, useEffect } from 'react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from './ui/sheet';
import { flowService } from '../services/flowService';
import type { FlowRunSummary } from '../services/flowApi';
import { Loader2, RefreshCw, PlayCircle } from 'lucide-react';
import { Button } from './ui/button';
import { Badge } from './ui/badge';

interface FlowRunHistoryProps {
    flowId: string;
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onSelectRun: (runId: string) => void;
}

export function FlowRunHistory({ flowId, open, onOpenChange, onSelectRun }: FlowRunHistoryProps) {
    const [runs, setRuns] = useState<FlowRunSummary[]>([]);
    const [loading, setLoading] = useState(false);

    const fetchRuns = async () => {
        if (!flowId) return;
        setLoading(true);
        try {
            const data = await flowService.listFlowRuns(flowId);
            setRuns(data || []);
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (open) {
            fetchRuns();
        }
    }, [open, flowId]);

    return (
        <Sheet open={open} onOpenChange={onOpenChange}>
            <SheetContent className="w-[400px] sm:w-[500px] overflow-y-auto">
                <SheetHeader className="mb-6">
                    <div className="flex items-center justify-between">
                        <SheetTitle className="flex items-center gap-2">
                            <PlayCircle className="w-5 h-5 text-muted-foreground" />
                            Run History
                        </SheetTitle>
                        <Button variant="ghost" size="icon" onClick={fetchRuns} disabled={loading} title="Refresh">
                            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                        </Button>
                    </div>
                    <SheetDescription>
                        Recent executions for this flow
                    </SheetDescription>
                </SheetHeader>

                <div className="space-y-3">
                    {loading && runs.length === 0 ? (
                        <div className="flex justify-center p-8">
                            <Loader2 className="animate-spin w-6 h-6 text-muted-foreground" />
                        </div>
                    ) : runs.length === 0 ? (
                        <div className="text-center p-8 text-sm text-muted-foreground bg-muted/30 rounded-lg border border-dashed">
                            No runs found for this flow.
                        </div>
                    ) : (
                        runs.map((run) => (
                            <div
                                key={run.name}
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
                                    {run.started_at && <span title={run.started_at}>{new Date(run.started_at).toLocaleString()}</span>}
                                </div>
                            </div>
                        ))
                    )}
                </div>
            </SheetContent>
        </Sheet>
    );
}
