import { useState, useEffect } from 'react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from './ui/sheet';
import { flowService } from '../services/flowService';
import type { FlowRunDetail } from '../services/flowApi';
import { Loader2, Box, CheckCircle2, XCircle, Clock, Check, X, Play, AlertTriangle } from 'lucide-react';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Textarea } from './ui/textarea';
import { toast } from '@/lib/toast';
import { useOptionalFlowContext } from '../contexts/FlowContext';
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from './ui/alert-dialog';
import { formatAbsoluteTime, useSiteTimezone } from '@/lib/serverTime';
import { calculateDuration, formatTimeAgo } from '@/utils/time';
import { humanizeFlowError } from '@/lib/flowValidation';
import { describeDecision, isFailedStepOutput, titleNodeIds, withoutFailureKeys } from '@/lib/flowRunFormat';
import { deskDocUrl, summarizeDocPayload } from '@/lib/flowRunDoc';
import { connectPath, notConnectedService } from '@/lib/flowIntegrations';
import { redactSecrets, summarizeToolOutput } from '@/lib/flowToolSummary';
import { Link } from 'react-router-dom';

function DocFieldValue({ field }: { field: { key: string; value: string; full?: string } }) {
    const [open, setOpen] = useState(false);
    if (!field.full) return <>{field.value}</>;
    return (
        <>
            <span data-testid={`flow-run-document-value-${field.key}`}>{open ? field.full : field.value}</span>{' '}
            <button
                type="button"
                className="text-xs font-medium text-primary underline"
                data-testid={`flow-run-document-more-${field.key}`}
                onClick={() => setOpen((v) => !v)}
            >
                {open ? 'Show less' : 'Show more'}
            </button>
        </>
    );
}

interface FlowRunViewerProps {
    runId: string | null;
    onClose: () => void;
}

/** Engine errors name the node id and the internal edge rule; show the step title and the actual reason. */
function readableRunError(message: string, labelOf: (id?: string | null) => string): string {
    const m = /^Node '([^']+)' of type '[^']+' failed and declares no on_error successor: ([\s\S]*)$/.exec(message);
    return m ? `${labelOf(m[1])} failed: ${m[2]}` : message;
}

function TimeValue({ value }: { value: string | null | undefined }) {
    if (!value) return <span className="text-muted-foreground">Not available</span>;
    return (
        <span title={formatTimeAgo(value)}>
            {formatAbsoluteTime(value)}
        </span>
    );
}

export function FlowRunViewer({ runId, onClose }: FlowRunViewerProps) {
    useSiteTimezone();
    const [confirmFail, setConfirmFail] = useState(false);
    const [run, setRun] = useState<FlowRunDetail | null>(null);
    const [loading, setLoading] = useState(false);
    const [resumePayload, setResumePayload] = useState<string>('');
    const activeFlow = useOptionalFlowContext()?.activeFlow;
    // A step saved without a title comes back from the server under its id: fall back to the editor's title for it.
    const titleOf = (nodeId: string): string | null => {
        const fromRun = run?.node_labels?.[nodeId];
        if (fromRun && fromRun !== nodeId) return fromRun;
        const fromFlow = activeFlow?.nodes.find((n) => n.id === nodeId)?.data.label;
        return typeof fromFlow === 'string' && fromFlow ? fromFlow : fromRun || null;
    };
    const labelOf = (nodeId: string | null | undefined) => (nodeId && titleOf(nodeId)) || nodeId || 'N/A';

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

    // Same fallback as the run list: refresh while the run is still queued or running.
    const active = run?.status === 'Queued' || run?.status === 'Running';
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

    const handleApproval = async (decision: 'approved' | 'rejected') => {
        if (!runId) return;
        setLoading(true);
        try {
            if (decision === 'approved') {
                await flowService.approveFlowRun(runId);
            } else {
                await flowService.rejectFlowRun(runId);
            }
            toast.success(decision === 'approved' ? 'Approved. The flow will continue.' : 'Rejected. The flow will follow its rejected path.');
            onClose();
        } catch (err) {
            toast.error(decision === 'approved' ? 'Could not approve this run' : 'Could not reject this run', {
                description: err instanceof Error ? err.message : 'Unknown error'
            });
            setLoading(false);
        }
    };

    const refreshRun = async () => {
        if (!runId) return;
        const data = await flowService.getFlowRun(runId);
        if (data) setRun(data);
    };

    const handleMarkFailed = async () => {
        if (!runId) return;
        setConfirmFail(false);
        try {
            await flowService.markFlowRunFailed(runId);
            toast.success('Run marked as failed.');
            await refreshRun();
        } catch (err) {
            toast.error('Could not mark this run as failed', { description: humanizeFlowError(err) });
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
            <SheetContent className="w-[500px] sm:w-[700px] sm:max-w-[90vw] overflow-y-auto" data-testid="flow-run-details">
                <SheetHeader className="mb-6">
                    <SheetTitle className="flex items-center gap-2">
                        <Box className="w-5 h-5 text-muted-foreground" />
                        Run details
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
                                <div className="font-medium text-sm" data-testid="flow-run-current-node">{labelOf(run.current_node_id)}</div>
                            </div>
                            <div className="flex-1">
                                <div className="text-xs text-muted-foreground mb-1">Hops</div>
                                <div className="font-medium text-sm">{run.hop_count}</div>
                            </div>
                        </div>

                        <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm" data-testid="flow-run-meta">
                            <div>
                                <div className="text-xs text-muted-foreground">Flow</div>
                                <div className="font-medium" data-testid="flow-run-flow-name">{run.flow_name || run.flow_id}</div>
                            </div>
                            <div>
                                <div className="text-xs text-muted-foreground">Started by</div>
                                <div className="font-medium" data-testid="flow-run-trigger">{run.trigger_type || 'Not available'}</div>
                            </div>
                            <div>
                                <div className="text-xs text-muted-foreground">Started</div>
                                <div data-testid="flow-run-started"><TimeValue value={run.started_at} /></div>
                            </div>
                            <div>
                                <div className="text-xs text-muted-foreground">Finished</div>
                                <div data-testid="flow-run-finished"><TimeValue value={run.completed_at} /></div>
                            </div>
                            {run.completed_at && (
                                <div>
                                    <div className="text-xs text-muted-foreground">Duration</div>
                                    <div data-testid="flow-run-duration">{calculateDuration(run.started_at, run.completed_at)}</div>
                                </div>
                            )}
                        </div>

                        {run.stale && (
                            <div className="flex items-start gap-3 rounded-md border border-warning/40 bg-warning-tint/50 p-4" data-testid="flow-run-stale">
                                <AlertTriangle className="w-4 h-4 mt-0.5 text-warning" />
                                <div className="flex-1 text-sm">
                                    <div className="font-medium">This run looks stuck</div>
                                    <p className="text-muted-foreground mt-0.5">
                                        It has been {run.status} for more than {run.stale_after_minutes} minutes without any change.
                                        {run.can_mark_failed ? '' : ' A System Manager can mark it as failed.'}
                                    </p>
                                    {run.can_mark_failed && (
                                        <Button size="sm" variant="outline" className="mt-3" data-testid="flow-run-mark-failed" onClick={() => setConfirmFail(true)}>
                                            Mark as failed
                                        </Button>
                                    )}
                                </div>
                            </div>
                        )}

                        {run.status === 'Failed' && run.last_error && (
                            <div data-testid="flow-run-error">
                                <h3 className="text-sm font-semibold mb-3">Error</h3>
                                <div className="bg-destructive/10 border border-destructive/30 text-destructive p-4 rounded-md text-xs font-mono overflow-x-auto whitespace-pre-wrap">
                                    {readableRunError(run.last_error, labelOf)}
                                </div>
                                {run.current_node_id && (
                                    <div className="text-xs text-muted-foreground mt-2">
                                        Failed at step <span className="font-medium">{labelOf(run.current_node_id)}</span>
                                    </div>
                                )}
                            </div>
                        )}

                        {(() => {
                            const { __node_outputs__: rawOutputs, ...input } = run.context_json ?? {};
                            const outputs = (rawOutputs && typeof rawOutputs === 'object' ? rawOutputs : {}) as Record<string, unknown>;
                            // A step whose own result says it did not succeed (tools return success:false) must never show as done.
                            const stepFailed = (id: string, output: unknown) =>
                                (run.status === 'Failed' && id === run.current_node_id) ||
                                isFailedStepOutput(output);
                            const steps = Object.entries(outputs).map(([id, output]) => ({ id, output, failed: stepFailed(id, output) }));
                            if (run.status === 'Failed' && run.current_node_id && !(run.current_node_id in outputs)) {
                                steps.push({ id: run.current_node_id, output: undefined, failed: true });
                            }
                            // Why a step failed: its own result's error, else the run-level error when this is the node the run stopped at.
                            const stepReason = (id: string, output: unknown): string | null => {
                                const own = output && typeof output === 'object' ? (output as { error?: unknown }).error : null;
                                if (typeof own === 'string' && own) return own;
                                if (run.status === 'Failed' && id === run.current_node_id && run.last_error) {
                                    const full = readableRunError(run.last_error, labelOf);
                                    const prefix = `${labelOf(id)} failed: `;
                                    return full.startsWith(prefix) ? full.slice(prefix.length) : full;
                                }
                                return null;
                            };
                            const isEmpty = (o: unknown) =>
                                o === undefined || o === null || o === '' || (typeof o === 'object' && Object.keys(o as object).length === 0);
                            return (
                                <>
                                    <div data-testid="flow-run-steps">
                                        <h3 className="text-sm font-semibold mb-3">Steps that ran</h3>
                                        {steps.length === 0 ? (
                                            <p className="text-xs text-muted-foreground">No step output was recorded for this run.</p>
                                        ) : (
                                            <ol className="space-y-2">
                                                {steps.map((st) => (
                                                    <li
                                                        key={st.id}
                                                        data-testid={`flow-run-step-${st.id}`}
                                                        data-step-status={st.failed ? 'failed' : 'done'}
                                                        className="rounded-md border p-3"
                                                    >
                                                        <div className="flex items-center gap-2 text-sm font-medium">
                                                            {st.failed ? <XCircle className="w-4 h-4 text-destructive" /> : <CheckCircle2 className="w-4 h-4 text-good" />}
                                                            {labelOf(st.id)}
                                                            <span className="text-xs font-normal text-muted-foreground">{st.failed ? 'Failed' : 'Done'}</span>
                                                        </div>
                                                        {describeDecision(st.output) && (
                                                            <div className="mt-1 text-sm" data-testid={`flow-run-decision-${st.id}`}>
                                                                {describeDecision(st.output)}
                                                                {typeof (st.output as { comment?: unknown }).comment === 'string' && (st.output as { comment: string }).comment
                                                                    ? <span className="text-muted-foreground">: "{(st.output as { comment: string }).comment}"</span>
                                                                    : null}
                                                            </div>
                                                        )}
                                                        {st.failed && stepReason(st.id, st.output) && (
                                                            <div className="mt-2 rounded border border-destructive/30 bg-destructive/10 p-2 text-xs text-destructive whitespace-pre-wrap" data-testid={`flow-run-step-error-${st.id}`}>
                                                                {stepReason(st.id, st.output)}
                                                                {notConnectedService(stepReason(st.id, st.output)) && (
                                                                    <Link
                                                                        to={connectPath(notConnectedService(stepReason(st.id, st.output)) as string)}
                                                                        className="ml-2 font-medium underline"
                                                                        data-testid={`flow-run-step-connect-${st.id}`}
                                                                    >
                                                                        Connect
                                                                    </Link>
                                                                )}
                                                            </div>
                                                        )}
                                                        {(() => {
                                                            // The reason is already shown above for a failed step: do not print it again in the output.
                                                            const shown = titleNodeIds(
                                                                st.failed && stepReason(st.id, st.output) ? withoutFailureKeys(st.output) : st.output,
                                                                titleOf,
                                                            );
                                                            if (isEmpty(shown)) return null;
                                                            // Tokens and auth headers never reach the screen, summarised or not.
                                                            const safe = redactSecrets(shown);
                                                            const toolId = activeFlow?.nodes.find((n) => n.id === st.id)?.data.actionConfig;
                                                            const summary = st.failed
                                                                ? null
                                                                : summarizeToolOutput(toolId && toolId.type === 'tool-call' ? toolId.tool_id : undefined, st.output);
                                                            const raw = (
                                                                <pre data-testid={`flow-run-step-output-${st.id}`} className="mt-2 bg-muted p-2 rounded text-xs font-mono overflow-x-auto whitespace-pre-wrap">
                                                                    {typeof safe === 'string' ? safe : JSON.stringify(safe, null, 2)}
                                                                </pre>
                                                            );
                                                            return summary ? (
                                                                <>
                                                                    <div className="mt-1 text-sm" data-testid={`flow-run-step-summary-${st.id}`}>{summary}</div>
                                                                    <details className="mt-1" data-testid={`flow-run-step-raw-${st.id}`}>
                                                                        <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">Show raw response</summary>
                                                                        {raw}
                                                                    </details>
                                                                </>
                                                            ) : raw;
                                                        })()}
                                                    </li>
                                                ))}
                                            </ol>
                                        )}
                                    </div>
                                    {(() => {
                                        const doc = summarizeDocPayload(input, run.trigger_event);
                                        const raw = (
                                            <div data-testid="flow-run-input" className="bg-muted p-4 rounded-md border text-xs font-mono overflow-x-auto whitespace-pre-wrap">
                                                {JSON.stringify(input, null, 2)}
                                            </div>
                                        );
                                        if (!doc) {
                                            return (
                                                <div>
                                                    <h3 className="text-sm font-semibold mb-3">Trigger input</h3>
                                                    {raw}
                                                </div>
                                            );
                                        }
                                        return (
                                            <div data-testid="flow-run-document">
                                                <h3 className="text-sm font-semibold mb-3">Document</h3>
                                                <div className="rounded-md border p-4 space-y-3">
                                                    <div className="text-sm">
                                                        <span className="font-medium" data-testid="flow-run-document-doctype">{doc.doctype}</span>{' '}
                                                        <a className="font-mono text-xs text-primary underline" href={deskDocUrl(doc.doctype, doc.name)} target="_blank" rel="noreferrer" data-testid="flow-run-document-name">{doc.name}</a>
                                                        {doc.event && (
                                                            <span className="ml-2 rounded-full border px-2 py-0.5 text-xs text-muted-foreground" data-testid="flow-run-document-event">
                                                                {doc.event}
                                                            </span>
                                                        )}
                                                    </div>
                                                    {doc.fields.length > 0 && (
                                                        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm" data-testid="flow-run-document-fields">
                                                            {doc.fields.map((f) => (
                                                                <div key={f.key} className="contents">
                                                                    <dt className="text-xs text-muted-foreground pt-0.5">{f.label}</dt>
                                                                    <dd className="break-words whitespace-pre-wrap">
                                                                        <DocFieldValue field={f} />
                                                                    </dd>
                                                                </div>
                                                            ))}
                                                        </dl>
                                                    )}
                                                </div>
                                                <details className="mt-3 text-xs" data-testid="flow-run-full-payload">
                                                    <summary className="cursor-pointer text-muted-foreground">Full payload</summary>
                                                    <div className="mt-2">{raw}</div>
                                                </details>
                                            </div>
                                        );
                                    })()}
                                </>
                            );
                        })()}

                        {run.status?.startsWith('Waiting') && run.waiting && Object.keys(run.waiting).length > 0 && (
                            <div>
                                <h3 className="text-sm font-semibold mb-3 text-warning">Pending Actions</h3>
                                <div className="bg-warning-tint/50 p-4 rounded-md border border-warning/25">
                                    {run.waiting.type === 'approval' ? (
                                        <div className="space-y-4">
                                            <div>
                                                <h4 className="font-semibold text-warning">{run.waiting.title as string || 'Approval Required'}</h4>
                                                {((run.waiting.instructions || run.waiting.message) as string) && (
                                                    <p className="text-sm text-warning mt-1" data-testid="flow-run-approval-message">{(run.waiting.instructions || run.waiting.message) as string}</p>
                                                )}
                                            </div>
                                            {(run.waiting.context_summary as string) && (
                                                <div className="bg-background/80 p-3 rounded text-sm text-muted-foreground whitespace-pre-wrap">
                                                    {run.waiting.context_summary as string}
                                                </div>
                                            )}
                                            <div className="flex items-center gap-3 pt-2">
                                                <Button size="sm" data-testid="flow-run-approve" onClick={() => handleApproval('approved')} className="bg-good hover:bg-good/90 text-panel gap-2">
                                                    <Check className="w-4 h-4" /> Approve
                                                </Button>
                                                <Button size="sm" variant="outline" data-testid="flow-run-reject" onClick={() => handleApproval('rejected')} className="text-destructive border-destructive hover:bg-destructive/10 gap-2">
                                                    <X className="w-4 h-4" /> Reject
                                                </Button>
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="space-y-3">
                                            <div className="text-xs font-mono overflow-x-auto">
                                                {JSON.stringify(titleNodeIds(run.waiting, titleOf), null, 2)}
                                            </div>
                                            <div className="space-y-2">
                                                <div className="text-xs text-muted-foreground">
                                                    Optional JSON input to merge into context when resuming:
                                                </div>
                                                <Textarea
                                                    className="min-h-[80px] text-xs font-mono"
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
            <AlertDialog open={confirmFail} onOpenChange={setConfirmFail}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Mark this run as failed?</AlertDialogTitle>
                        <AlertDialogDescription>
                            The run will be stopped and recorded as failed. This cannot be undone.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction data-testid="flow-run-mark-failed-confirm" onClick={handleMarkFailed}>Mark as failed</AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </Sheet>
    );
}
