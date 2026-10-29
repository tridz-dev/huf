import { useEffect, useState, type KeyboardEvent } from 'react';
import { Play, History, Upload, Loader2, Save, CheckCircle2, Circle, Settings, Pencil, CircleOff } from 'lucide-react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Button } from './ui/button';
import { Input } from './ui/input';
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
import { useFlowContext } from '../contexts/FlowContext';
import { getFlowIntegrationStatus, runFlow } from '../services/flowApi';
import { unconnectedSteps } from '@/lib/flowIntegrations';
import { toast } from '@/lib/toast';
import { FlowRunHistory } from './FlowRunHistory';
import { FlowRunViewer } from './FlowRunViewer';
import { FlowSettingsModal } from './modals/FlowSettingsModal';
import { BLOCKED_TOAST_ID, humanizeFlowError, summarizeIssues, validateFlow } from '@/lib/flowValidation';
import { reportFlowRun } from '@/lib/flowRunToast';
import { RunFlowDialog } from './flow/RunFlowDialog';
import { FlowHelpPopover } from './flow/FlowHelpPopover';
import { DisabledReason } from './flow/DisabledReason';
import { useFlowPermissions } from '@/hooks/useFlowPermissions';
import { publishBlockedReason } from '@/lib/flowPublishGuard';
import { codePublishBlockedReason } from '@/lib/codeFlow';
import { useCodeFlowStatus } from '@/lib/useCodeFlowStatus';
import { useRunParam } from '@/hooks/useRunParam';

/**
 * Left-aligned "Flows > flow name [pencil]" control for the flow canvas
 * toolbar. Replaces the floating InlineEditName panel that used to sit over
 * the canvas — this renders in the toolbar row itself instead, reusing the
 * same rename plumbing (`activeFlow.name` + `updateFlowName`).
 */
export function FlowToolbarTitle() {
  const { activeFlow, updateFlowName } = useFlowContext();
  const [isEditing, setIsEditing] = useState(false);
  const [draftName, setDraftName] = useState('');

  if (!activeFlow) {
    return (
      <span className="text-[13px] text-steel truncate">Flows</span>
    );
  }

  const startEditing = () => {
    setDraftName(activeFlow.name);
    setIsEditing(true);
  };

  const commit = () => {
    setIsEditing(false);
    const trimmed = draftName.trim();
    if (trimmed && trimmed !== activeFlow.name) {
      void updateFlowName(activeFlow.id, trimmed);
    }
  };

  const revert = () => {
    setIsEditing(false);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      commit();
    } else if (event.key === 'Escape') {
      event.preventDefault();
      revert();
    }
  };

  return (
    <div className="flex items-center gap-1.5 min-w-0">
      <Link to="/flows" className="text-[13px] text-steel hover:text-ink shrink-0 transition-colors">
        Flows
      </Link>
      <span className="text-[13px] text-steel shrink-0">/</span>
      {isEditing ? (
        <Input
          value={draftName}
          onChange={(event) => setDraftName(event.target.value)}
          onBlur={commit}
          onKeyDown={handleKeyDown}
          autoFocus
          className="h-6 text-[13px] font-medium text-ink border-0 px-1 py-0 focus-visible:ring-1 min-w-0 max-w-[240px]"
        />
      ) : (
        <span className="text-[13px] font-medium text-ink truncate max-w-[240px]">
          {activeFlow.name || 'Untitled flow'}
        </span>
      )}
      <Button
        type="button"
        variant="ghost"
        size="icon"
        aria-label="Edit flow name"
        onClick={startEditing}
        disabled={isEditing}
        className="h-6 w-6 shrink-0 text-steel hover:text-ink"
      >
        <Pencil className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}

export function FlowsHeaderActions() {
  const { activeFlow, saveState, hasUnsavedChanges, saveFlow, setSelectedNode, setFlowPublished } = useFlowContext();
  const [showRunDialog, setShowRunDialog] = useState(false);
  const { canManage, canPublishSensitive, readOnlyReason } = useFlowPermissions();
  const [isPublishing, setIsPublishing] = useState(false);
  const [showUnpublish, setShowUnpublish] = useState(false);
  const [isUnpublishing, setIsUnpublishing] = useState(false);
  const isPublished = activeFlow?.status === 'active';
  // A Data trigger or a web request step needs an extra permission to publish; say why Publish is off.
  const { status: codeStatus } = useCodeFlowStatus();
  const publishBlocked =
    publishBlockedReason(activeFlow?.nodes ?? [], canPublishSensitive) ??
    codePublishBlockedReason(activeFlow?.nodes ?? [], codeStatus);
  const [showHistory, setShowHistory] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [selectedRunId, setSelectedRunId] = useRunParam();

  const location = useLocation();
  const navigate = useNavigate();

  const openSettingsFromUrl = () => {
    const sp = new URLSearchParams(location.search);
    return sp.get('settings') === '1';
  };

  useEffect(() => {
    if (openSettingsFromUrl()) setShowSettings(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search]);

  const handleCloseSettings = () => {
    setShowSettings(false);
    const sp = new URLSearchParams(location.search);
    if (sp.has('settings')) {
      navigate({ pathname: location.pathname, search: '' }, { replace: true });
    }
  };

  const issues = activeFlow ? validateFlow(activeFlow.nodes, activeFlow.edges, 'run') : [];

  /** Block with a readable message (and select the offending step) instead of a raw schema error. */
  const blockedBy = (purpose: 'save' | 'run'): boolean => {
    if (!activeFlow) return true;
    const found = validateFlow(activeFlow.nodes, activeFlow.edges, purpose);
    if (found.length === 0) return false;
    if (found[0].nodeId) setSelectedNode(found[0].nodeId);
    toast.error(purpose === 'save' ? "Can't save yet" : 'Finish setting up your flow first', {
      id: BLOCKED_TOAST_ID,
      description: `Finish setting up ${summarizeIssues(found)}`,
    });
    return true;
  };

  const saveIfNeeded = async (what: string): Promise<boolean> => {
    if (!hasUnsavedChanges) return true;
    if (blockedBy('save')) return false;
    try {
      await saveFlow();
      return true;
    } catch (err) {
      toast.error(`Could not save before ${what}`, { description: humanizeFlowError(err) });
      return false;
    }
  };

  /** Check and save the flow, then ask for the input data before running. */
  const handleRun = async () => {
    if (!activeFlow || blockedBy('run')) return;
    if (!(await saveIfNeeded('running'))) return;
    setShowRunDialog(true);
  };

  const startRun = async (payload: Record<string, unknown>) => {
    if (!activeFlow) return;
    try {
      reportFlowRun(await runFlow(activeFlow.id, payload));
    } catch (err) {
      toast.error('Could not run the flow', { description: humanizeFlowError(err) });
    }
  };

  const handleSaveDraft = async () => {
    if (blockedBy('save')) return;
    try {
      await saveFlow();
      toast.success('Flow saved');
    } catch (err) {
      toast.error('Could not save the flow', { description: humanizeFlowError(err) });
    }
  };

  const handlePublish = async () => {
    if (!activeFlow || blockedBy('run')) return;
    if (!(await saveIfNeeded('publishing'))) return;

    setIsPublishing(true);
    try {
      await setFlowPublished(activeFlow.id, true);
      toast.success('Flow published', { description: 'Its trigger is on now: the webhook accepts calls, and schedule or record triggers start runs. Unpublish to turn it off.' });
      // Non-blocking: publishing works, but these steps will fail until their integration is connected.
      const missing = unconnectedSteps(activeFlow.nodes, await getFlowIntegrationStatus());
      if (missing.length > 0) {
        toast.warning('Some steps are not connected yet', {
          description: `${missing.map((m) => (m.stepLabel === m.service ? m.stepLabel : `${m.stepLabel} (${m.service})`)).join(', ')} will fail until you connect them.`,
          id: 'flow-unconnected-warning',
        });
      }
    } catch (err) {
      toast.error('Could not publish the flow', { description: humanizeFlowError(err) });
    } finally {
      setIsPublishing(false);
    }
  };

  const handleUnpublish = async () => {
    if (!activeFlow) return;
    setIsUnpublishing(true);
    try {
      await setFlowPublished(activeFlow.id, false);
      toast.success('Flow unpublished', { description: 'It is a draft again. Its triggers no longer start it.' });
      setShowUnpublish(false);
    } catch (err) {
      toast.error('Could not unpublish the flow', { description: humanizeFlowError(err) });
    } finally {
      setIsUnpublishing(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      {/* Save State Indicator (bare dot + text, no chip background) */}
      {activeFlow && (
        <div className="flex items-center gap-1.5 mr-2 text-muted-foreground" data-testid="flow-save-state" title={issues.length > 0 ? ` to finish before it can run` : undefined}>
          {issues.length > 0 && (
            <button
              type="button"
              data-testid="flow-validation-summary"
              className="mr-2 hidden text-xs text-signal-ink underline-offset-2 hover:underline xl:inline"
              onClick={() => issues[0].nodeId && setSelectedNode(issues[0].nodeId)}
            >
              {issues.length === 1 ? '1 thing to finish' : `${issues.length} things to finish`}
            </button>
          )}
          {saveState === 'saving' ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : saveState === 'error' ? (
            <Circle className="w-3.5 h-3.5 text-destructive" />
          ) : hasUnsavedChanges ? (
            <Circle className="w-3.5 h-3.5 text-signal fill-signal" />
          ) : (
            <CheckCircle2 className="w-3.5 h-3.5 text-good" />
          )}
          <span className="text-xs font-medium">
            {saveState === 'saving' ? 'Saving...' :
              saveState === 'error' ? 'Save Failed' :
                hasUnsavedChanges ? 'Unsaved' : 'Saved'}
          </span>
        </div>
      )}

      <FlowHelpPopover />

      {/* Save Draft Button */}
      <Button
        variant="outline"
        size="sm"
        className="gap-2"
        data-testid="flow-save"
        aria-label="Save"
        title="Save your changes (Ctrl/Cmd+S)"
        onClick={handleSaveDraft}
        disabled={!activeFlow || saveState === 'saving' || !hasUnsavedChanges}
      >
        <Save className="w-4 h-4" />
        <span className="hidden xl:inline">Save</span>
      </Button>

      {/* Runs Button */}
      <Button
        variant="outline"
        size="sm"
        className="gap-2"
        data-testid="flow-runs"
        aria-label="Runs"
        title="Runs: see every run of this flow and what each step did"
        onClick={() => setShowHistory(true)}
        disabled={!activeFlow}
      >
        <History className="w-4 h-4" />
        <span className="hidden xl:inline">Runs</span>
      </Button>

      {/* Settings Button */}
      <Button
        variant="outline"
        size="sm"
        className="gap-2"
        data-testid="flow-settings"
        aria-label="Settings"
        title="Settings: name, description and category"
        onClick={() => setShowSettings(true)}
        disabled={!activeFlow}
      >
        <Settings className="w-4 h-4" />
        <span className="hidden xl:inline">Settings</span>
      </Button>

      {/* Run Button */}
      <DisabledReason reason={canManage ? null : readOnlyReason}>
        <Button
          variant="outline"
          size="sm"
          className="gap-2"
          data-testid="flow-run"
          aria-label="Run"
          title="Run now: starts the flow once with the input you choose"
          onClick={handleRun}
          disabled={!activeFlow || !canManage}
        >
          <Play className="w-4 h-4" />
          <span className="hidden xl:inline">Run</span>
        </Button>
      </DisabledReason>

      {/* Publish / Unpublish */}
      {isPublished && (
        <span
          className="inline-flex items-center gap-1 rounded-full border border-good/40 px-2 py-0.5 text-xs font-medium text-good"
          data-testid="flow-published-badge"
        >
          <CheckCircle2 className="w-3 h-3" />
          Published
        </span>
      )}
      <DisabledReason reason={!canManage ? readOnlyReason : isPublished ? null : publishBlocked}>
        {isPublished ? (
          <Button
            variant="outline"
            size="sm"
            className="gap-2"
            data-testid="flow-unpublish"
            title="Unpublish: turn the triggers off. The flow becomes a draft again"
            onClick={() => setShowUnpublish(true)}
            disabled={!activeFlow || isUnpublishing || !canManage}
          >
            <CircleOff className="w-4 h-4" />
            <span>Unpublish</span>
          </Button>
        ) : (
          <Button
            variant="display"
            size="sm"
            className="gap-2"
            data-testid="flow-publish"
            title="Publish: turn the trigger on so the flow starts by itself (webhook calls, schedule or record changes)"
            onClick={handlePublish}
            disabled={!activeFlow || isPublishing || !canManage || !!publishBlocked}
          >
            {isPublishing ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Upload className="w-4 h-4" />
            )}
            <span>Publish</span>
          </Button>
        )}
      </DisabledReason>

      <AlertDialog open={showUnpublish} onOpenChange={setShowUnpublish}>
        <AlertDialogContent data-testid="flow-unpublish-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Unpublish "{activeFlow?.name}"?</AlertDialogTitle>
            <AlertDialogDescription>
              The flow goes back to a draft. Its webhook is refused and its schedule and document triggers stop starting
              it. Runs already in progress finish. Publish it again whenever you want to turn it back on.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              data-testid="flow-unpublish-confirm"
              disabled={isUnpublishing}
              onClick={(e) => {
                e.preventDefault();
                void handleUnpublish();
              }}
            >
              {isUnpublishing ? 'Unpublishing...' : 'Unpublish'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {activeFlow && (
        <FlowRunHistory
          flowId={activeFlow.id}
          open={showHistory}
          onOpenChange={setShowHistory}
          onSelectRun={setSelectedRunId}
        />
      )}
      <FlowRunViewer
        runId={selectedRunId}
        onClose={() => setSelectedRunId(null)}
      />
      <RunFlowDialog
        open={showRunDialog}
        flowId={activeFlow?.id ?? null}
        flowName={activeFlow?.name}
        onOpenChange={setShowRunDialog}
        onRun={startRun}
      />
      <FlowSettingsModal
        open={showSettings}
        onClose={handleCloseSettings}
      />
    </div>
  );
}
