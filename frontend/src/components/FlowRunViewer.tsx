import { useState } from 'react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from './ui/sheet';
import { flowService } from '../services/flowService';
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
import { useSiteTimezone } from '@/lib/serverTime';
import { calculateDuration, formatTimeAgo } from '@/utils/time';
import { DocFieldValue, readableRunError, TimeValue } from './flow/RunViewerParts';
import { useFlowRunDetail } from '@/hooks/flow/useFlowRunDetail';
import { runTimesSentence } from '@/lib/flow-run/flowTimeZone';
import { humanizeFlowError } from '@/lib/flow-graph/flowValidation';
import { describeDecision, flowRunStatusLabel, isFailedStepOutput, titleNodeIds } from '@/lib/flow-run/flowRunFormat';
import { deskDocUrl, summarizeDocPayload } from '@/lib/flow-run/flowRunDoc';
import { decisionMovedRun } from '@/lib/flow-run/flowRunDecision';
import { connectPath, notConnectedService } from '@/lib/flow/flowIntegrations';
import { redactSecrets } from '@/lib/flow/flowToolSummary';
import { HumanValue } from '@/components/common/HumanValue';
import { RunStepOutput } from './flow/RunStepOutput';
import { friendlyRunTitle, humanizeMessageText, placeTriggerInput, startedByWords } from '@/lib/flow-run/humanize';
import { useFlowRunIdentity } from '@/hooks/flow/useFlowRunIdentity';
import { useUser } from '@/contexts/UserContext';
import { Link } from 'react-router-dom';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';

interface FlowRunViewerProps {
    runId: string | null;
    onClose: () => void;
}

export function FlowRunViewer({ runId, onClose }: FlowRunViewerProps) {
    const siteZone = useSiteTimezone();
    const { canManage } = useFlowPermissions();
    const [confirmFail, setConfirmFail] = useState(false);
    const { run, loading, setLoading, refreshRun } = useFlowRunDetail(runId);
    const [resumePayload, setResumePayload] = useState<string>('');
    const activeFlow = useOptionalFlowContext()?.activeFlow;
    const { user } = useUser();
    const identity = useFlowRunIdentity(runId);
    const runTitle = friendlyRunTitle({
        runNumber: identity?.run_number,
        startedBy: run ? startedByWords({ triggerType: run.trigger_type, owner: identity?.started_by, ownerName: identity?.started_by_name, currentUser: user?.name }) : null,
        ago: run?.started_at ? formatTimeAgo(run.started_at) : null,
    });
    // A step saved without a title comes back from the server under its id: fall back to the editor's title for it.
    const titleOf = (nodeId: string): string | null => {
        const fromRun = run?.node_labels?.[nodeId];
        if (fromRun && fromRun !== nodeId) return fromRun;
        const fromFlow = activeFlow?.nodes.find((n) => n.id === nodeId)?.data.label;
        return typeof fromFlow === 'string' && fromFlow ? fromFlow : fromRun || null;
    };
    // Names for ids that show up inside step data and text (router choice, approval targets...).
    const stepNames: Record<string, string> = Object.fromEntries(Object.keys(run?.node_labels ?? {}).map((id) => [id, titleOf(id) ?? id]));
    const labelOf = (nodeId: string | null | undefined) => (nodeId && titleOf(nodeId)) || nodeId || 'N/A';

    const handleApproval = async (decision: 'approved' | 'rejected') => {
        if (!runId) return;
        setLoading(true);
        try {
            const stepDecided = run?.current_node_id;
            const answer = decision === 'approved'
                ? await flowService.approveFlowRun(runId)
                : await flowService.rejectFlowRun(runId);
            if (!decisionMovedRun(answer, stepDecided)) {
                toast.error(decision === 'approved' ? 'Could not approve this run' : 'Could not reject this run', {
                    description: 'The run did not move on, so nothing was recorded. Please try again.',
                });
                await refreshRun();
                setLoading(false);
                return;
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
            <SheetContent className="flex w-full max-w-full flex-col gap-0 overflow-hidden p-0 sm:w-[700px] sm:max-w-[90vw]" data-testid="flow-run-details">
                <SheetHeader className="shrink-0 border-b border-border bg-background px-6 pb-4 pt-6 pr-12" data-testid="flow-run-details-header">
                    <SheetTitle className="flex items-center gap-2">
                        <Box className="w-5 h-5 text-muted-foreground" />
                        Run details
                    </SheetTitle>
                    <SheetDescription data-testid="flow-run-title" data-run-id={runId}>
                        {runTitle}
                    </SheetDescription>
                </SheetHeader>

                <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5" data-testid="flow-run-details-body">
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
                                    {(run.status === 'Waiting Approval' || run.status === 'Waiting Code') && <Clock className="w-3 h-3 mr-1" />}
                                    {flowRunStatusLabel(run.status)}
                                </Badge>
                            </div>
                            <div className="flex-1">
                                <div className="text-xs text-muted-foreground mb-1">Last step</div>
                                <div className="font-medium text-sm" data-testid="flow-run-current-node">{labelOf(run.current_node_id)}</div>
                            </div>
                            <div className="flex-1">
                                <div className="text-xs text-muted-foreground mb-1" title="How many steps the run has gone through">Steps run</div>
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

                        <p className="-mt-3 text-meta text-muted-foreground" data-testid="flow-run-timezone-note">{runTimesSentence(siteZone)}</p>

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
                            const placement = summarizeDocPayload(input, run.trigger_event) ? ({ mode: 'none' } as const) : placeTriggerInput(input, steps);
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
                                                                {canManage && notConnectedService(stepReason(st.id, st.output)) && (
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
                                                        <RunStepOutput
                                                            stepId={st.id}
                                                            output={st.output}
                                                            failed={st.failed}
                                                            reasonShown={!!stepReason(st.id, st.output)}
                                                            decisionShown={!!describeDecision(st.output)}
                                                            names={stepNames}
                                                            titleOf={titleOf}
                                                            toolId={(() => { const cfg = activeFlow?.nodes.find((n) => n.id === st.id)?.data.actionConfig; return cfg && cfg.type === 'tool-call' ? cfg.tool_id : undefined; })()}
                                                            dataReceived={placement.mode === 'merged' && placement.stepId === st.id ? input : undefined}
                                                        />
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
                                            // The data the run started with is shown once: inside the first step when that step repeats it.
                                            if (placement.mode === 'merged') return null;
                                            return (
                                                <div data-testid="flow-run-trigger-input">
                                                    <h3 className="text-sm font-semibold mb-3">Data this run started with</h3>
                                                    {placement.mode === 'none' ? (
                                                        <p className="text-xs text-muted-foreground" data-testid="flow-run-input-empty">No data was sent with this run.</p>
                                                    ) : (
                                                        <HumanValue value={redactSecrets(input)} names={stepNames} testId="flow-run-human-input" raw rawTitle="Raw data this run started with" rawTextTestId="flow-run-input" />
                                                    )}
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
                                    {run.waiting.type === 'code' ? (
                                        <p className="text-sm text-warning" data-testid="run-waiting-code-note">
                                            {run.waiting.approval
                                                ? 'Waiting for an administrator to approve this code run. Check the approvals bell.'
                                                : 'Running your code in a sandbox...'}
                                        </p>
                                    ) : run.waiting.type === 'approval' ? (
                                        <div className="space-y-4">
                                            <div>
                                                <h4 className="font-semibold text-warning">{run.waiting.title as string || 'Approval Required'}</h4>
                                                {((run.waiting.instructions || run.waiting.message) as string) && (
                                                    <p className="text-sm text-warning mt-1" data-testid="flow-run-approval-message">{humanizeMessageText((run.waiting.instructions || run.waiting.message) as string, { names: stepNames })}</p>
                                                )}
                                            </div>
                                            {(run.waiting.context_summary as string) && (
                                                <div className="bg-background/80 p-3 rounded text-sm text-muted-foreground whitespace-pre-wrap">
                                                    {humanizeMessageText(run.waiting.context_summary as string, { names: stepNames })}
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
                </div>
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
