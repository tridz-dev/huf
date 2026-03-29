import { useState, useEffect } from 'react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from './ui/sheet';
import { flowService } from '../services/flowService';
import type { FlowRunDetail } from '../services/flowApi';
import { Loader2, Box, CheckCircle2, XCircle, Clock, UserCheck, AlertCircle, ThumbsUp, ThumbsDown } from 'lucide-react';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Textarea } from './ui/textarea';
import { Alert, AlertDescription } from './ui/alert';

interface FlowRunViewerProps {
    runId: string | null;
    onClose: () => void;
}

export function FlowRunViewer({ runId, onClose }: FlowRunViewerProps) {
    const [run, setRun] = useState<FlowRunDetail | null>(null);
    const [loading, setLoading] = useState(false);
    const [actionLoading, setActionLoading] = useState<'approve' | 'reject' | null>(null);
    const [comment, setComment] = useState('');
    const [actionError, setActionError] = useState<string | null>(null);

    useEffect(() => {
        async function fetchRun() {
            if (!runId) return;
            setLoading(true);
            setActionError(null);
            setComment('');
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

    const handleApprove = async () => {
        if (!runId) return;
        setActionLoading('approve');
        setActionError(null);
        try {
            await flowService.approveFlowRun(runId, comment || undefined);
            // Refresh the run data
            const updatedRun = await flowService.getFlowRun(runId);
            if (updatedRun) setRun(updatedRun);
            setComment('');
        } catch (err: any) {
            setActionError(err?.message || 'Failed to approve flow run');
        } finally {
            setActionLoading(null);
        }
    };

    const handleReject = async () => {
        if (!runId) return;
        setActionLoading('reject');
        setActionError(null);
        try {
            await flowService.rejectFlowRun(runId, comment || undefined);
            // Refresh the run data
            const updatedRun = await flowService.getFlowRun(runId);
            if (updatedRun) setRun(updatedRun);
            setComment('');
        } catch (err: any) {
            setActionError(err?.message || 'Failed to reject flow run');
        } finally {
            setActionLoading(null);
        }
    };

    const isWaitingApproval = run?.status === 'Waiting Approval';

    // Extract approval info from waiting data if available
    const waitingInfo = run?.waiting as any;
    const approverRole = waitingInfo?.role || null;
    const approverUsers = waitingInfo?.users || [];
    const waitingNode = waitingInfo?.node_id || run?.current_node_id;
    const waitingSince = waitingInfo?.since || null;

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
                        {/* Status Card */}
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

                        {/* Approval UI - Only shown when waiting for approval */}
                        {isWaitingApproval && (
                            <div className="border border-orange-200 dark:border-orange-900 rounded-lg overflow-hidden">
                                {/* Approval Header */}
                                <div className="bg-orange-50 dark:bg-orange-950/30 p-4 border-b border-orange-200 dark:border-orange-900">
                                    <div className="flex items-center gap-2 mb-2">
                                        <UserCheck className="w-5 h-5 text-orange-600 dark:text-orange-400" />
                                        <h3 className="font-semibold text-orange-800 dark:text-orange-300">
                                            Approval Required
                                        </h3>
                                    </div>
                                    <p className="text-sm text-orange-700 dark:text-orange-400">
                                        This flow is waiting for approval at node <strong>{waitingNode}</strong>
                                    </p>
                                </div>

                                {/* Approver Info */}
                                <div className="p-4 bg-orange-50/30 dark:bg-orange-950/10 space-y-3">
                                    {approverRole && (
                                        <div className="flex items-center gap-2 text-sm">
                                            <span className="text-muted-foreground">Required Role:</span>
                                            <Badge variant="outline" className="font-mono text-xs">
                                                {approverRole}
                                            </Badge>
                                        </div>
                                    )}
                                    {approverUsers && approverUsers.length > 0 && (
                                        <div className="flex items-center gap-2 text-sm">
                                            <span className="text-muted-foreground">Can be approved by:</span>
                                            <div className="flex flex-wrap gap-1">
                                                {approverUsers.map((user: string, idx: number) => (
                                                    <Badge key={idx} variant="outline" className="text-xs">
                                                        {user}
                                                    </Badge>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                    {waitingSince && (
                                        <div className="text-sm text-muted-foreground">
                                            Waiting since: {new Date(waitingSince).toLocaleString()}
                                        </div>
                                    )}
                                </div>

                                {/* Error Display */}
                                {actionError && (
                                    <Alert variant="destructive" className="m-4 mb-0">
                                        <AlertCircle className="h-4 w-4" />
                                        <AlertDescription>{actionError}</AlertDescription>
                                    </Alert>
                                )}

                                {/* Comment Input */}
                                <div className="p-4 space-y-3">
                                    <div>
                                        <label className="text-sm font-medium mb-1.5 block">
                                            Comments (optional)
                                        </label>
                                        <Textarea
                                            placeholder="Add comments about your decision..."
                                            value={comment}
                                            onChange={(e) => setComment(e.target.value)}
                                            className="min-h-[80px] resize-none"
                                            disabled={!!actionLoading}
                                        />
                                    </div>

                                    {/* Action Buttons */}
                                    <div className="flex gap-3 pt-2">
                                        <Button
                                            variant="default"
                                            className="flex-1 bg-green-600 hover:bg-green-700 text-white"
                                            onClick={handleApprove}
                                            disabled={!!actionLoading}
                                        >
                                            {actionLoading === 'approve' ? (
                                                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                            ) : (
                                                <ThumbsUp className="w-4 h-4 mr-2" />
                                            )}
                                            Approve
                                        </Button>
                                        <Button
                                            variant="destructive"
                                            className="flex-1"
                                            onClick={handleReject}
                                            disabled={!!actionLoading}
                                        >
                                            {actionLoading === 'reject' ? (
                                                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                            ) : (
                                                <ThumbsDown className="w-4 h-4 mr-2" />
                                            )}
                                            Reject
                                        </Button>
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Context Variables */}
                        <div>
                            <h3 className="text-sm font-semibold mb-3">Context Variables</h3>
                            <div className="bg-muted p-4 rounded-md border text-xs font-mono overflow-x-auto whitespace-pre-wrap">
                                {JSON.stringify(run.context_json, null, 2)}
                            </div>
                        </div>

                        {/* Waiting Data (shown for non-approval waiting states or additional info) */}
                        {run.status?.startsWith('Waiting') && run.waiting && Object.keys(run.waiting).length > 0 && !isWaitingApproval && (
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
