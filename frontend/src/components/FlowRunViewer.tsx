import { useState, useEffect } from 'react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from './ui/sheet';
import { flowService } from '../services/flowService';
import type { FlowRunDetail } from '../services/flowApi';
import { Loader2, Box, CheckCircle2, XCircle, Clock } from 'lucide-react';
import { Badge } from './ui/badge';

interface FlowRunViewerProps {
    runId: string | null;
    onClose: () => void;
}

export function FlowRunViewer({ runId, onClose }: FlowRunViewerProps) {
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

    return (
        <Sheet open={!!runId} onOpenChange={(open) => !open && onClose()}>
            <SheetContent className="w-[500px] sm:w-[700px] sm:max-w-[90vw] overflow-y-auto">
                <SheetHeader className="mb-6">
                    <SheetTitle className="flex items-center gap-2">
                        <Box className="w-5 h-5 text-muted-foreground" />
                        Run Details
                    </SheetTitle>
                    <SheetDescription>
                        {runId}
                    </SheetDescription>
                </SheetHeader>

                {loading ? (
                    <div className="flex justify-center p-12">
                        <Loader2 className="animate-spin w-8 h-8 text-muted-foreground" />
                    </div>
                ) : !run ? (
                    <div className="text-center p-8 text-muted-foreground">Run not found</div>
                ) : (
                    <div className="space-y-6">
                        <div className="flex items-center gap-4 border p-4 rounded-lg bg-muted/20">
                            <div className="flex-1">
                                <div className="text-xs text-muted-foreground mb-1">Status</div>
                                <Badge variant={
                                    run.status === 'Success' ? 'default' :
                                        run.status === 'Failed' ? 'destructive' : 'secondary'
                                }>
                                    {run.status === 'Success' && <CheckCircle2 className="w-3 h-3 mr-1" />}
                                    {run.status === 'Failed' && <XCircle className="w-3 h-3 mr-1" />}
                                    {run.status === 'Waiting Approval' && <Clock className="w-3 h-3 mr-1" />}
                                    {run.status}
                                </Badge>
                            </div>
                            <div className="flex-1">
                                <div className="text-xs text-muted-foreground mb-1">Current/Last Node</div>
                                <div className="font-medium text-sm">{run.current_node_id || 'N/A'}</div>
                            </div>
                            <div className="flex-1">
                                <div className="text-xs text-muted-foreground mb-1">Hops</div>
                                <div className="font-medium text-sm">{run.hop_count}</div>
                            </div>
                        </div>

                        <div>
                            <h3 className="text-sm font-semibold mb-3">Context Variables</h3>
                            <div className="bg-muted p-4 rounded-md border text-xs font-mono overflow-x-auto whitespace-pre-wrap">
                                {JSON.stringify(run.context_json, null, 2)}
                            </div>
                        </div>

                        {run.status?.startsWith('Waiting') && run.waiting && Object.keys(run.waiting).length > 0 && (
                            <div>
                                <h3 className="text-sm font-semibold mb-3 text-orange-600">Pending Actions</h3>
                                <div className="bg-orange-50/50 dark:bg-orange-950/20 p-4 rounded-md border border-orange-200 dark:border-orange-900 text-xs font-mono overflow-x-auto">
                                    {JSON.stringify(run.waiting, null, 2)}
                                </div>
                            </div>
                        )}
                    </div>
                )}
            </SheetContent>
        </Sheet>
    );
}
