import { useEffect, useMemo, useRef, useState } from 'react';
import { FlaskConical, Loader2, Lock, Sparkles } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { HumanValue } from '@/components/common/HumanValue';
import { useFlowContext } from '@/contexts/FlowContext';
import { useFlowIssues } from '@/hooks/flow/useFlowIssues';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { useViewport } from '@/lib/ui/responsive';
import { issuesForStep } from '../frame/frameIssues';
import { useStepTest } from '@/hooks/flow/useStepTest';
import {
  AI_NOTE,
  aiAlreadyConfirmed,
  ageText,
  parseSampleInput,
  rememberAiConfirmed,
  testButtonHint,
  testButtonLabel,
} from '@/lib/flow-test/testModel';
import type { FlowNode, FlowNodeData } from '@/types/flow.types';
import type { StepSampleInput, StepTestResult } from '@/services/flow/stepTestApi';
import { SampleInputSection, SourceChip } from './SampleInputSection';
import { TestResultView } from './TestResultView';
import { TriggerTestSection } from './TriggerTestSection';

interface Props {
  node: FlowNode;
  /** The Test tab is the one on screen: the sample data is asked for again each time it opens. */
  active: boolean;
  onOpenSetup: () => void;
}

const VIEW_ONLY = 'Only people who can edit this flow can test its steps or see pinned samples. Ask a flow editor.';

/**
 * The Test tab of a step (UX-16): the sample data the step receives, a "Test step" button, the output and
 * "Pin this output". Testing never sends or changes anything outside the flow and leaves no run in the history.
 */
export function StepTestPanel({ node, active, onOpenSetup }: Props) {
  const { canManage } = useFlowPermissions();
  const { isPhone } = useViewport();
  if (isPhone) {
    return (
      <p className="rounded-md border border-dashed border-border p-3 text-sm text-muted-foreground" data-testid="flow-step-test-phone">
        Testing a step works best on a larger screen. Open this flow on a computer to try its steps.
      </p>
    );
  }
  if (!canManage) {
    return (
      <div className="flex items-start gap-3 rounded-md border border-border bg-muted/40 p-3 text-sm text-muted-foreground" data-testid="flow-step-test-viewonly">
        <Lock className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        <p>{VIEW_ONLY}</p>
      </div>
    );
  }
  return <EditableTest node={node} active={active} onOpenSetup={onOpenSetup} />;
}

function EditableTest({ node, active, onOpenSetup }: Props) {
  const { activeFlow, hasUnsavedChanges, saveFlow, updateNodeData } = useFlowContext();
  const flowId = activeFlow?.id;
  const [opened, setOpened] = useState(active);
  const [openCount, setOpenCount] = useState(active ? 1 : 0);
  const wasActive = useRef(active);
  useEffect(() => {
    if (active && !wasActive.current) {
      setOpened(true);
      setOpenCount((n) => n + 1);
    }
    wasActive.current = active;
  }, [active]);

  const issues = useFlowIssues();
  const unfinished = issuesForStep(issues, node.id);
  const t = useStepTest(flowId, node.id, opened, openCount);
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState('');
  const [saving, setSaving] = useState(false);
  const [confirmAi, setConfirmAi] = useState(false);
  const isTrigger = node.data.nodeType === 'trigger';
  const info = t.info;
  const pinned = node.data.sample !== undefined && node.data.sample !== null;
  const busy = t.running || saving;

  const originalText = useMemo(() => (info ? JSON.stringify(info.sample_input, null, 2) : ''), [info]);
  const toggleEdit = () => {
    if (!editing) setText(originalText);
    setEditing(!editing);
  };

  const pin = (result: StepTestResult) => {
    const value = result.pin_value;
    if (value === undefined || value === null) return;
    updateNodeData(node.id, (data) => ({ ...data, sample: value, sampleAt: new Date().toISOString() }) as FlowNodeData);
    toast.success('Pinned. Save the flow to keep it; the steps after this one then show these values as examples.');
  };
  const unpin = () => {
    updateNodeData(node.id, (data) => {
      const rest: FlowNodeData = { ...data };
      delete rest.sample;
      delete rest.sampleAt;
      return rest;
    });
    toast.success('Unpinned');
  };

  const saveFirst = async (): Promise<boolean> => {
    if (!hasUnsavedChanges) return true;
    setSaving(true);
    try {
      await saveFlow();
      return true;
    } catch (error) {
      t.setRunError(error instanceof Error && error.message ? error.message : 'Save the flow first, then test again.');
      return false;
    } finally {
      setSaving(false);
    }
  };

  const go = async (sample?: StepSampleInput | Record<string, unknown>) => {
    setConfirmAi(false);
    if (!(await saveFirst())) return;
    await t.run(sample);
    void t.reload();
  };

  const onRun = () => {
    let sample: Record<string, unknown> | undefined;
    if (editing) {
      const parsed = parseSampleInput(text);
      if (!parsed.ok) {
        t.setRunError(parsed.message);
        return;
      }
      sample = parsed.value;
    }
    if (info?.calls_ai && !aiAlreadyConfirmed()) {
      setConfirmAi(true);
      return;
    }
    void go(sample);
  };

  const onConfirmAi = () => {
    rememberAiConfirmed();
    const parsed = editing ? parseSampleInput(text) : null;
    void go(parsed && parsed.ok ? parsed.value : undefined);
  };

  const live = activeFlow?.status === 'active';

  if (t.infoState === 'loading' && !info) {
    return (
      <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground" role="status" data-testid="flow-step-test-loading">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> Getting the sample data ready...
      </div>
    );
  }
  if (t.infoState === 'error' && !info) {
    return (
      <div className="space-y-2 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm" role="alert" data-testid="flow-step-test-load-error">
        <p>{t.infoError}</p>
        <Button type="button" variant="outline" size="sm" onClick={() => void t.reload()} data-testid="flow-step-test-retry">Try again</Button>
      </div>
    );
  }
  if (!info || !flowId) return null;

  const pinState = { pinned, pinnedAt: node.data.sampleAt, onPin: () => t.result && pin(t.result), onUnpin: unpin };

  return (
    <div className="space-y-4" data-testid="flow-step-test" data-effect={info.effect}>
      {info.calls_ai && (
        <div className="flex items-start gap-2 rounded-md border border-signal/30 bg-signal/5 p-2.5 text-xs" data-testid="flow-step-test-ai-note">
          <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-signal-ink" aria-hidden />
          <span><span className="font-medium">{AI_NOTE}.</span> A test asks it for real, so it can use a little of your AI credit.</span>
        </div>
      )}

      {unfinished.length > 0 && !isTrigger && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-warning/30 bg-warning-tint p-2.5 text-xs text-warning" data-testid="flow-step-test-unfinished">
          <span className="min-w-0 flex-1 break-words">This step is not finished yet: {unfinished[0].message.replace(/\.$/, '')}. A test may fail until it is.</span>
          <Button type="button" variant="outline" size="sm" onClick={onOpenSetup} data-testid="flow-step-test-unfinished-fix">Open Setup</Button>
        </div>
      )}

      {isTrigger ? (
        <>
          <section aria-labelledby="step-test-trigger-title">
            <h3 id="step-test-trigger-title" className="mb-2 text-sm font-medium">Data this flow starts with</h3>
            {pinned ? (
              <div className="rounded-md border border-border bg-card p-3" data-testid="flow-step-test-trigger-sample">
                <div className="mb-2 flex flex-wrap items-center gap-x-2 gap-y-1">
                  <SourceChip source="trigger_sample" partKey="trigger" />
                  {node.data.sampleAt && <span className="text-meta text-muted-foreground" data-testid="flow-step-test-trigger-pinned">Pinned {ageText(node.data.sampleAt)}</span>}
                  <Button type="button" variant="ghost" size="sm" className="ml-auto" onClick={unpin} data-testid="flow-step-unpin-trigger">Unpin</Button>
                </div>
                <HumanValue value={node.data.sample} testId="flow-step-test-value-trigger" />
              </div>
            ) : (
              <p className="rounded-md border border-dashed border-border p-3 text-xs text-muted-foreground" data-testid="flow-step-test-trigger-empty">
                No sample yet. Bring in a real one below and pin it, so the steps after this one can offer real values.
              </p>
            )}
          </section>
          <TriggerTestSection
            flowId={flowId}
            nodeId={node.id}
            kind={info.trigger_kind}
            doctype={info.doctype}
            live={live}
            running={busy}
            onResult={(r) => t.setResult(r)}
            onTick={() => void go()}
          />
        </>
      ) : (
        <>
          <SampleInputSection
            parts={info.parts}
            editing={editing}
            text={text}
            onText={setText}
            onToggleEdit={toggleEdit}
            onReset={() => setText(originalText)}
            canEdit
          />
          <div className="space-y-1.5">
            <Button type="button" className="w-full" onClick={onRun} disabled={busy} data-testid="flow-step-test-run" data-simulated={info.simulated}>
              {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : <FlaskConical className="mr-2 h-4 w-4" aria-hidden />}
              {busy ? (saving ? 'Saving...' : 'Testing...') : testButtonLabel(info)}
            </Button>
            <p className="text-xs text-muted-foreground" data-testid="flow-step-test-hint">{testButtonHint(info)}</p>
          </div>
          {confirmAi && (
            <div className="space-y-2 rounded-md border border-border bg-muted/40 p-3 text-sm" role="alertdialog" aria-label="Ask the AI model?" data-testid="flow-step-test-ai-confirm">
              <p>This asks the AI model for real and can use a little of your AI credit. You will not be asked again in this browser.</p>
              <div className="flex gap-2">
                <Button type="button" size="sm" onClick={onConfirmAi} data-testid="flow-step-test-ai-confirm-yes">Test anyway</Button>
                <Button type="button" size="sm" variant="ghost" onClick={() => setConfirmAi(false)} data-testid="flow-step-test-ai-confirm-no">Cancel</Button>
              </div>
            </div>
          )}
        </>
      )}

      {t.runError && <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/5 p-2.5 text-xs" data-testid="flow-step-test-run-error">{t.runError}</p>}
      {busy && (
        <p role="status" className="flex items-center gap-2 text-xs text-muted-foreground" data-testid="flow-step-test-running">
          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> {saving ? 'Saving your changes first...' : 'Testing. A step can take up to 30 seconds.'}
        </p>
      )}

      {t.result ? (
        <section aria-labelledby="step-test-result-title">
          <h3 id="step-test-result-title" className="mb-2 text-sm font-medium">Result</h3>
          <TestResultView result={t.result} pin={pinState} onOpenSetup={onOpenSetup} isTrigger={isTrigger} />
        </section>
      ) : (
        !isTrigger && <PinnedOnly pinned={pinned} at={node.data.sampleAt} sample={node.data.sample} onUnpin={unpin} />
      )}
      {hasUnsavedChanges && !isTrigger && (
        <p className="text-meta text-muted-foreground" data-testid="flow-step-test-save-note">Your latest changes are saved first, so the test uses what you see.</p>
      )}
    </div>
  );
}

function PinnedOnly({ pinned, at, sample, onUnpin }: { pinned: boolean; at?: string; sample: unknown; onUnpin: () => void }) {
  if (!pinned) return null;
  return (
    <section data-testid="flow-step-pinned-only" aria-label="Pinned sample">
      <div className="mb-2 flex items-center gap-2">
        <span className="mr-auto text-xs text-muted-foreground" data-testid="flow-step-pinned">Pinned {at ? ageText(at) : ''}</span>
        <Button type="button" variant="ghost" size="sm" onClick={onUnpin} data-testid="flow-step-unpin">Unpin</Button>
      </div>
      {sample !== undefined && <HumanValue value={sample} raw rawTitle="Pinned sample" testId="flow-step-pinned-value" />}
    </section>
  );
}
