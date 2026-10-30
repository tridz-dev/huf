import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, Loader2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from './ui/sheet';
import { flowService } from '../services/flowService';
import { Button } from './ui/button';
import { toast } from '@/lib/toast';
import { useOptionalFlowContext } from '../contexts/FlowContext';
import { useSiteTimezone } from '@/lib/serverTime';
import { useFlowRunDetail } from '@/hooks/flow/useFlowRunDetail';
import { humanizeFlowError } from '@/lib/flow-graph/flowValidation';
import { decisionMovedRun } from '@/lib/flow-run/flowRunDecision';
import { describeJsonProblem } from '@/lib/flow-run/jsonErrors';
import { friendlyRunTitle, startedByWords } from '@/lib/flow-run/humanize';
import { buildRunStory } from '@/lib/flow-run/story/runSteps';
import { runHeadline, startedLine } from '@/lib/flow-run/story/headline';
import { useFlowRunIdentity } from '@/hooks/flow/useFlowRunIdentity';
import { useUser } from '@/contexts/UserContext';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { RunDecisionBar } from './flow/decision/RunDecisionBar';
import { useViewport } from '@/lib/ui/responsive';
import { OutcomeChip, RunStatusPill } from './flow/run/RunStatusBits';
import { RunStepCard } from './flow/run/RunStepCard';
import { RunStatusBanner } from './flow/run/RunStatusBanner';
import { RunWaitingCard } from './flow/run/RunWaitingCard';
import { RunDetailsFold } from './flow/run/RunDetailsFold';
import { RunInputBlocks } from './flow/run/RunInputBlocks';

interface FlowRunViewerProps {
    runId: string | null;
    onClose: () => void;
    /** Opened from the run history: a "Run history" link in the header goes back to that list. */
    onBack?: () => void;
}

export function FlowRunViewer({ runId, onClose, onBack }: FlowRunViewerProps) {
    const siteZone = useSiteTimezone();
    const navigate = useNavigate();
    const { isPhone } = useViewport();
    const { canManage } = useFlowPermissions();
    const { run, loading, setLoading, refreshRun } = useFlowRunDetail(runId);
    const [resumePayload, setResumePayload] = useState<string>('');
    const flowContext = useOptionalFlowContext();
    const activeFlow = flowContext?.activeFlow;
    const { user } = useUser();
    const identity = useFlowRunIdentity(runId);
    const bodyRef = useRef<HTMLDivElement>(null);

    // A step saved without a title comes back from the server under its id: fall back to the editor's title for it.
    const titleOf = (nodeId: string): string | null => {
        const fromRun = run?.node_labels?.[nodeId];
        if (fromRun && fromRun !== nodeId) return fromRun;
        const fromFlow = activeFlow?.nodes.find((n) => n.id === nodeId)?.data.label;
        return typeof fromFlow === 'string' && fromFlow ? fromFlow : fromRun || null;
    };
    // Names for ids that show up inside step data and text (router choice, approval targets...).
    const stepNames: Record<string, string> = Object.fromEntries(Object.keys(run?.node_labels ?? {}).map((id) => [id, titleOf(id) ?? id]));
    const toolIdOf = (id: string) => {
        const cfg = activeFlow?.nodes.find((n) => n.id === id)?.data.actionConfig;
        return cfg && cfg.type === 'tool-call' ? cfg.tool_id : undefined;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
    const story = useMemo(() => (run ? buildRunStory(run, { titleOf }) : null), [run, activeFlow]);

    const startedWords = run ? startedByWords({ triggerType: run.trigger_type, owner: run.started_by ?? identity?.started_by, ownerName: run.started_by_name ?? identity?.started_by_name, currentUser: user?.name }) : '';
    const runTitle = friendlyRunTitle({ runNumber: run?.run_number ?? identity?.run_number });

    // The step that needs attention (failed or waiting) is brought into view once the run is shown.
    const shownFor = useRef<string | null>(null);
    useEffect(() => {
        if (!run || !story || shownFor.current === run.flow_run_id) return;
        shownFor.current = run.flow_run_id;
        const target = bodyRef.current?.querySelector('[data-step-status="failed"], [data-step-status="waiting"]');
        target?.scrollIntoView?.({ block: 'nearest' });
    }, [run, story]);
    useEffect(() => { if (!runId) shownFor.current = null; }, [runId]);

    const openStep = (nodeId: string) => {
        if (!run) return;
        if (flowContext && activeFlow?.id === run.flow_id) {
            flowContext.setSelectedNode(nodeId);
            onClose();
        } else {
            navigate(`/flows/${encodeURIComponent(run.flow_id)}?step=${encodeURIComponent(nodeId)}`);
        }
    };

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

    const handleStop = async () => {
        if (!runId) return;
        try {
            await flowService.markFlowRunFailed(runId);
            toast.success('Run stopped.');
            await refreshRun();
        } catch (err) {
            toast.error('Could not stop this run', { description: humanizeFlowError(err) });
        }
    };

    const handleCancel = async () => {
        if (!runId) return;
        try {
            await flowService.cancelFlowRun(runId);
            toast.success('Run cancelled.');
            await refreshRun();
        } catch (err) {
            toast.error('Could not cancel this run', { description: humanizeFlowError(err) });
        }
    };

    const handleResume = async () => {
        if (!runId) return;
        let parsed: Record<string, unknown> | undefined;
        if (resumePayload.trim()) {
            const problem = describeJsonProblem(resumePayload);
            if (problem) {
                toast.error('The extra information is not valid', { description: problem.message });
                return;
            }
            parsed = JSON.parse(resumePayload);
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

    const headline = run ? runHeadline(run) : null;
    const lastStep = run?.current_node_id ? (titleOf(run.current_node_id) ?? '') : '';

    return (
        <Sheet open={!!runId} onOpenChange={(open) => !open && onClose()}>
            <SheetContent side={isPhone ? 'bottom' : 'right'} className="flex w-full max-w-full flex-col gap-0 overflow-hidden p-0 max-sm:h-[92dvh] max-sm:rounded-t-xl sm:w-[clamp(420px,62vw,640px)] sm:max-w-none" data-testid="flow-run-details">
                <SheetHeader className="shrink-0 border-b border-border bg-background px-4 pb-4 pt-4 pr-12 sm:px-6 sm:pt-6" data-testid="flow-run-details-header">
                    {onBack && (
                        <Button type="button" variant="ghost" size="sm" className="-ml-2 mb-1 w-fit gap-1.5 px-2 max-[1023px]:min-h-11" data-testid="flow-run-back" onClick={onBack}>
                            <ArrowLeft className="h-4 w-4" aria-hidden /> Run history
                        </Button>
                    )}
                    <SheetTitle data-testid="flow-run-title" data-run-id={runId}>
                        {runTitle}{run?.flow_name ? <span className="font-normal text-steel"> · {run.flow_name}</span> : null}
                    </SheetTitle>
                    <SheetDescription data-testid="flow-run-started-by">
                        {run ? startedLine(startedWords, run.started_at) : 'Loading the run...'}
                    </SheetDescription>
                </SheetHeader>

                <div ref={bodyRef} className="min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-6" data-testid="flow-run-details-body">
                {loading && !run ? (
                    <div className="flex justify-center p-12">
                        <Loader2 className="animate-spin w-8 h-8 text-muted-foreground" />
                    </div>
                ) : !run || !story || !headline ? (
                    <div className="text-center p-8 text-muted-foreground">Run not found</div>
                ) : (
                    <div className="space-y-5 pb-6">
                        <div data-testid="flow-run-headline">
                            <div className="flex flex-wrap items-center gap-2">
                                <RunStatusPill status={run.status} stale={run.stale} />
                                {run.outcome && <OutcomeChip outcome={run.outcome} />}
                            </div>
                            <h2 className="mt-2 text-lg font-semibold leading-snug text-ink" data-testid="flow-run-headline-text">{headline.headline}</h2>
                            {headline.sub && <p className="mt-0.5 text-sm text-steel" data-testid="flow-run-headline-sub">{headline.sub}</p>}
                        </div>

                        <RunStatusBanner run={run} canManage={canManage} onStop={handleStop} onCancel={handleCancel} />

                        <RunWaitingCard
                            run={run}
                            names={stepNames}
                            titleOf={titleOf}
                            busy={loading}
                            phone={isPhone}
                            onDecide={handleApproval}
                            resumePayload={resumePayload}
                            onResumePayload={setResumePayload}
                            onResume={handleResume}
                        />

                        <section data-testid="flow-run-steps">
                            <h3 className="mb-3 text-sm font-semibold text-ink">What happened</h3>
                            {story.steps.length === 0 ? (
                                <p className="text-sm text-steel" data-testid="flow-run-steps-empty">
                                    {run.status === 'Queued' ? 'Nothing has run yet.' : 'No step output was recorded for this run.'}
                                </p>
                            ) : (
                                <ol className="space-y-2" data-testid="flow-run-timeline">
                                    {story.steps.map((st) => (
                                        <RunStepCard key={st.id} step={st} names={stepNames} titleOf={titleOf} toolIdOf={toolIdOf} canManage={canManage} onOpenStep={openStep} />
                                    ))}
                                </ol>
                            )}
                        </section>

                        <RunInputBlocks story={story} triggerEvent={run.trigger_event} names={stepNames} />

                        <RunDetailsFold run={run} runId={run.flow_run_id} siteZone={siteZone} stepCount={story.stepCount} lastStep={lastStep} startedWords={startedWords} />
                    </div>
                )}
                </div>
                {isPhone && run?.status === 'Waiting Approval' && run.waiting?.type === 'approval' && (
                    <RunDecisionBar sticky canDecide={run.can_decide !== false} reason={run.cannot_decide_reason} busy={loading} onDecide={handleApproval} />
                )}
            </SheetContent>
        </Sheet>
    );
}
