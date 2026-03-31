import { useState, useEffect } from 'react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from './ui/sheet';
import { flowService } from '../services/flowService';
import type { FlowRunDetail } from '../services/flowApi';
import { Loader2, Box, CheckCircle2, XCircle, Clock, Check, X, Play } from 'lucide-react';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { toast } from 'sonner';

interface FlowRunViewerProps {
    runId: string | null;
    onClose: () => void;
}

export function FlowRunViewer({ runId, onClose }: FlowRunViewerProps) {
    const [run, setRun] = useState<FlowRunDetail | null>(null);
    const [loading, setLoading] = useState(false);
    const [resumePayload, setResumePayload] = useState<string>('');

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

    const handleApproval = async (decision: 'approved' | 'rejected') => {
        if (!runId) return;
        setLoading(true);
        try {
            if (decision === 'approved') {
                await flowService.approveFlowRun(runId);
            } else {
                await flowService.rejectFlowRun(runId);
            }
            toast.success(`Flow run ${decision} successfully`);
            onClose();
        } catch (err) {
            toast.error(`Failed to ${decision} flow run`, {
                description: err instanceof Error ? err.message : 'Unknown error'
            });
            setLoading(false);
        }
    };

    const handleResume = async () => {
        if (!runId) return;
        let parsed: Record<string, unknown> | undefined;
        if (resumePayload.trim()) {
            try {
                parsed = JSON.parse(resumePayload);
            } catch (err) {
                toast.error('Invalid JSON payload', {
                    description: err instanceof Error ? err.message : 'Unable to parse JSON',
                });
                return;
            }
        }
        setLoading(true);
        try {
            await flowService.resumeFlowRun(runId, parsed);
            toast.success('Flow run resumed');
            onClose();
        } catch (err) {
            toast.error('Failed to resume flow run', {
                description: err instanceof Error ? err.message : 'Unknown error',
            });
            setLoading(false);
        }
    };

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
                                <div className="bg-orange-50/50 dark:bg-orange-950/20 p-4 rounded-md border border-orange-200 dark:border-orange-900">
                                    {run.waiting.type === 'approval' ? (
                                        <div className="space-y-4">
                                            <div>
                                                <h4 className="font-semibold text-orange-800 dark:text-orange-400">{run.waiting.title as string || 'Approval Required'}</h4>
                                                {(run.waiting.instructions as string) && (
                                                    <p className="text-sm text-orange-700 dark:text-orange-500 mt-1">{run.waiting.instructions as string}</p>
                                                )}
                                            </div>
                                            {(run.waiting.context_summary as string) && (
                                                <div className="bg-background/80 p-3 rounded text-sm text-muted-foreground whitespace-pre-wrap">
                                                    {run.waiting.context_summary as string}
                                                </div>
                                            )}
                                            <div className="flex items-center gap-3 pt-2">
                                                <Button size="sm" onClick={() => handleApproval('approved')} className="bg-green-600 hover:bg-green-700 text-white gap-2">
                                                    <Check className="w-4 h-4" /> Approve
                                                </Button>
                                                <Button size="sm" variant="outline" onClick={() => handleApproval('rejected')} className="text-destructive border-destructive hover:bg-destructive/10 gap-2">
                                                    <X className="w-4 h-4" /> Reject
                                                </Button>
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="space-y-3">
                                            <div className="text-xs font-mono overflow-x-auto">
                                                {JSON.stringify(run.waiting, null, 2)}
                                            </div>
                                            <div className="space-y-2">
                                                <div className="text-xs text-muted-foreground">
                                                    Optional JSON input to merge into context when resuming:
                                                </div>
                                                <textarea
                                                    className="w-full min-h-[80px] rounded-md border bg-background px-2 py-1 text-xs font-mono"
                                                    value={resumePayload}
                                                    onChange={(e) => setResumePayload(e.target.value)}
                                                    placeholder='e.g. { "user_input": "yes" }'
                                                    disabled={loading}
                                                />
                                                <div className="flex justify-end">
                                                    <Button
                                                        size="sm"
                                                        onClick={handleResume}
                                                        disabled={loading}
                                                        className="gap-2"
                                                    >
                                                        <Play className="w-4 h-4" /> Resume Flow
                                                    </Button>
                                                </div>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>
                )}
            </SheetContent>
        </Sheet>
    );
}
