import { useEffect, useState, type KeyboardEvent } from 'react';
import { Play, History, Upload, Loader2, Save, CheckCircle2, Circle, Settings, Pencil, CircleOff, Eye } from 'lucide-react';
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
import { unconnectedSteps } from '@/lib/flow/flowIntegrations';
import { toast } from '@/lib/toast';
import { FlowRunHistory } from './FlowRunHistory';
import { FlowRunViewer } from './FlowRunViewer';
import { FlowSettingsModal } from './modals/FlowSettingsModal';
import { humanizeFlowError, validateFlow } from '@/lib/flow-graph/flowValidation';
import { FlowChecklist } from './flow/frame/FlowChecklist';
import { setChecklistOpen } from './flow/frame/frameStore';
import { useFlowIssues } from './flow/frame/useFlowIssues';
import { reportFlowRun } from '@/lib/flow-run/flowRunToast';
import { RunFlowDialog } from './flow/RunFlowDialog';
import { FlowHelpPopover } from './flow/FlowHelpPopover';
import { DisabledReason } from './flow/DisabledReason';
import { FLOW_VIEW_ONLY_HINT, useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { publishBlockedReason } from '@/lib/flow/flowPublishGuard';
import { codePublishBlockedReason } from '@/lib/flow-graph/codeFlow';
import { useCodeFlowStatus } from '@/lib/flow-graph/useCodeFlowStatus';
import { useRunParam } from '@/hooks/flow/useRunParam';
import { flowStatusKind, StatusPill } from './common/StatusPill';

/**
 * Left-aligned "Flows > flow name [pencil]" control for the flow canvas
 * toolbar. Replaces the floating InlineEditName panel that used to sit over
 * the canvas — this renders in the toolbar row itself instead, reusing the
 * same rename plumbing (`activeFlow.name` + `updateFlowName`).
 */
export function FlowToolbarTitle() {
  const { activeFlow, updateFlowName } = useFlowContext();
  const { canManage } = useFlowPermissions();
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
          className="h-6 text-[13px] font-medium text-ink border-0 px-1 py-0 focus-visible:ring-1 min-w-0 max-w-[160px] xl:max-w-[240px]"
        />
      ) : (
        <span className="text-[13px] font-medium text-ink truncate max-w-[130px] xl:max-w-[240px]" title={activeFlow.name}>
          {activeFlow.name || 'Untitled flow'}
        </span>
      )}
      {canManage ? (
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
      ) : (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <span
                tabIndex={0}
                className="inline-flex shrink-0 items-center gap-1 rounded-full border border-line bg-paper-deep px-2 py-0.5 text-xs font-medium text-steel"
                data-testid="flow-view-only-pill"
              >
                <Eye className="h-3 w-3" aria-hidden />
                View only
              </span>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="max-w-[260px]" data-testid="flow-view-only-pill-hint">
              {FLOW_VIEW_ONLY_HINT}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      )}
    </div>
  );
}

export function FlowsHeaderActions() {
  const { activeFlow, saveState, hasUnsavedChanges, saveFlow, setFlowPublished, getFlow } = useFlowContext();
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

  const issues = useFlowIssues();

  /**
   * Running and publishing need a finished flow. When it is not, open the list of what is left (each row has a Fix
   * button) instead of failing quietly or with a toast. Saving is never blocked, except for a live flow, which
   * triggers start from what is stored and so has to stay finished.
   */
  const needsFinishing = (): boolean => {
    // Read the flow as it is right now: a field the person just typed in may not have reached this render yet.
    const latest = getFlow();
    if (!activeFlow || !latest || validateFlow(latest.nodes, latest.edges).length === 0) return false;
    setChecklistOpen(true);
    return true;
  };

  const saveIfNeeded = async (what: string): Promise<boolean> => {
    if (!hasUnsavedChanges) return true;
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
    if (!activeFlow || needsFinishing()) return;
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
    if (isPublished && needsFinishing()) return;
    try {
      await saveFlow();
      toast.success('Flow saved');
    } catch (err) {
      toast.error('Could not save the flow', { description: humanizeFlowError(err) });
    }
  };

  const handlePublish = async () => {
    if (!activeFlow || needsFinishing()) return;
    if (!(await saveIfNeeded('publishing'))) return;

    setIsPublishing(true);
    try {
      await setFlowPublished(activeFlow.id, true);
      toast.success('Flow is live', { description: 'Its trigger is on now: the webhook accepts calls, and schedule or record triggers start runs. Unpublish to turn it off.' });
      // Non-blocking: publishing works, but these steps will fail until their integration is connected.
      const missing = unconnectedSteps(activeFlow.nodes, await getFlowIntegrationStatus());
      if (missing.length > 0) {
        toast.warning('Some steps are not connected yet', {
          description: `${missing.map((m) => (m.stepLabel === m.service ? m.stepLabel : `${m.stepLabel} (${m.service})`)).join(', ')} will fail until you connect them.`,
          id: 'flow-unconnected-warning',
        });
      }
    } catch (err) {
      toast.error('Could not make the flow live', { description: humanizeFlowError(err) });
    } finally {
      setIsPublishing(false);
    }
  };

  const handleUnpublish = async () => {
    if (!activeFlow) return;
    setIsUnpublishing(true);
    try {
      await setFlowPublished(activeFlow.id, false);
      toast.success('Flow is a draft again', { description: 'It is no longer live. Its triggers no longer start it.' });
      setShowUnpublish(false);
    } catch (err) {
      toast.error('Could not turn the flow off', { description: humanizeFlowError(err) });
    } finally {
      setIsUnpublishing(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      {/* Save state: "Saved" and, next to it, what is left to finish (opens the list) */}
      {activeFlow && (
        <div className="flex items-center gap-1.5 mr-2 text-muted-foreground" data-testid="flow-save-state">
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
          {canManage && <FlowChecklist live={isPublished} />}
        </div>
      )}

      <FlowHelpPopover />

      {/* Save Draft Button */}
      <DisabledReason reason={canManage ? null : readOnlyReason}>
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
      </DisabledReason>

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
        title={canManage ? 'Settings: name, description and category' : 'Settings: see the name, description and category'}
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
      {activeFlow && (
        <span data-testid={isPublished ? 'flow-published-badge' : 'flow-draft-badge'} className="inline-flex">
          <StatusPill
            kind={flowStatusKind(activeFlow.status, issues.length)}
            data-testid="flow-status-pill"
            title={isPublished ? 'Live: the trigger is on' : 'Draft: the trigger is off until you publish'}
          />
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
            <span className="sr-only xl:not-sr-only">Unpublish</span>
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
            <span className="sr-only xl:not-sr-only">Publish</span>
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
