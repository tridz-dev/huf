import { useEffect, useState } from 'react';
import { Play, History, Upload, Loader2, Save, CheckCircle2, Circle, Settings, CircleOff } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Button } from './ui/button';
import { useFlowContext } from '../contexts/FlowContext';
import { FlowRunHistory } from './FlowRunHistory';
import { FlowRunViewer } from './FlowRunViewer';
import { FlowSettingsModal } from './modals/FlowSettingsModal';
import { ConvertToProcedureDialog } from './ConvertToProcedureDialog';
import { FlowChecklist } from './flow/frame/FlowChecklist';
import { useFlowIssues } from '@/hooks/flow/useFlowIssues';
import { useFrozenWhilePressed } from '@/hooks/flow/useFrozenWhilePressed';
import { RunFlowDialog } from './flow/RunFlowDialog';
import { PublishFlowDialog } from './flow/publish/PublishFlowDialog';
import { UnpublishFlowDialog } from './flow/publish/UnpublishFlowDialog';
import { FlowHelpPopover } from './flow/FlowHelpPopover';
import { DisabledReason } from './flow/DisabledReason';
import { HeaderOverflowMenu } from './flow/header/HeaderOverflowMenu';
import { useFlowHeaderActions } from './flow/header/useFlowHeaderActions';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { publishBlockedReason } from '@/lib/flow/flowPublishGuard';
import { codePublishBlockedReason } from '@/lib/flow-graph/codeFlow';
import { useCodeFlowStatus } from '@/lib/flow-graph/useCodeFlowStatus';
import { useConvertedProcedure } from './flow/canvas/useCanvasEffects';
import { usePhoneFlowView } from './flow/phone/usePhoneFlowView';
import { useRunParam } from '@/hooks/flow/useRunParam';
import { useStepParam } from '@/hooks/flow/useStepParam';
import { flowStatusKind, StatusPill } from './common/StatusPill';
import { HIT_TARGET, useViewport } from '@/lib/ui/responsive';
import { cn } from '@/lib/utils';

export { FlowToolbarTitle } from './flow/header/FlowToolbarTitle';

/**
 * The editor's header buttons. Above 1200px everything is on show; at 1200px and narrower Help, Run history, Flow settings,
 * Tidy layout, Convert to procedure and the status move into a "..." menu, leaving the save state, Save, a labelled Run and a
 * labelled Publish. On a phone the editing buttons go and Run (or "Run test" on a draft), Publish and "..." remain.
 */
export function FlowsHeaderActions() {
  const { activeFlow, saveState, hasUnsavedChanges, tidyLayout } = useFlowContext();
  const { canManage, canPublishSensitive, readOnlyReason } = useFlowPermissions();
  const { isCompact, isPhone } = useViewport();
  const header = useFlowHeaderActions();
  const isPublished = activeFlow?.status === 'active';
  // A Data trigger or a web request step needs an extra permission to publish; say why Publish is off.
  const { status: codeStatus } = useCodeFlowStatus();
  const publishBlocked =
    publishBlockedReason(activeFlow?.nodes ?? [], canPublishSensitive) ??
    codePublishBlockedReason(activeFlow?.nodes ?? [], codeStatus);
  const [showHistory, setShowHistory] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showConvert, setShowConvert] = useState(false);
  const [selectedRunId, setSelectedRunId] = useRunParam();
  useStepParam();
  const phoneView = usePhoneFlowView();
  const convertedProcedure = useConvertedProcedure(isCompact && !isPhone ? activeFlow?.id : undefined, activeFlow?.version, saveState);

  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    if (new URLSearchParams(location.search).get('settings') === '1') setShowSettings(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search]);

  const handleCloseSettings = () => {
    setShowSettings(false);
    if (new URLSearchParams(location.search).has('settings')) {
      navigate({ pathname: location.pathname, search: '' }, { replace: true });
    }
  };

  const issues = useFlowIssues();
  // The status word changes with the count: hold it while a button is pressed (see useFrozenWhilePressed).
  const statusKind = flowStatusKind(activeFlow?.status, useFrozenWhilePressed(issues.length));
  const hit = cn('gap-2', HIT_TARGET);
  const showSaveState = !!activeFlow && !isPhone;

  const publishButton = isPublished ? (
    <Button
      variant="outline"
      size="sm"
      className={hit}
      data-testid="flow-unpublish"
      title="Unpublish: turn the triggers off. The flow becomes a draft again"
      onClick={() => header.setShowUnpublish(true)}
      disabled={!activeFlow || header.isUnpublishing || !canManage}
    >
      <CircleOff className="w-4 h-4" />
      Unpublish
    </Button>
  ) : (
    <Button
      variant={isPhone ? 'outline' : 'display'}
      size="sm"
      className={hit}
      data-testid="flow-publish"
      title="Publish: turn the trigger on so the flow starts by itself (webhook calls, schedule or record changes)"
      onClick={header.handlePublish}
      disabled={!activeFlow || header.isPublishing || !canManage || !!publishBlocked}
    >
      {header.isPublishing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
      Publish
    </Button>
  );

  return (
    <div className="flex items-center gap-2">
      {/* Save state (bare dot + text, no chip background). Nothing is edited on a phone, so it has none. */}
      {showSaveState && (
        <div className="mr-1 flex items-center gap-1.5 text-muted-foreground" data-testid="flow-save-state">
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
            {saveState === 'saving' ? 'Saving...' : saveState === 'error' ? 'Save Failed' : hasUnsavedChanges ? 'Unsaved' : 'Saved'}
          </span>
          {canManage && <FlowChecklist live={isPublished} />}
        </div>
      )}

      {isPhone && canManage && <FlowChecklist live={isPublished} separator={false} />}

      {!isCompact && <FlowHelpPopover />}

      {/* Save Draft Button: a label from 1200px up, an icon (with its name for screen readers) when narrow */}
      {!isPhone && (
        <DisabledReason reason={canManage ? null : readOnlyReason}>
          <Button
            variant="outline"
            size="sm"
            className={hit}
            data-testid="flow-save"
            aria-label="Save"
            title="Save your changes (Ctrl/Cmd+S)"
            onClick={header.handleSaveDraft}
            disabled={!activeFlow || saveState === 'saving' || !hasUnsavedChanges}
          >
            <Save className="w-4 h-4" />
            {!isCompact && 'Save'}
          </Button>
        </DisabledReason>
      )}

      {!isCompact && (
        <>
          <Button variant="outline" size="sm" className={hit} data-testid="flow-runs" aria-label="Runs" title="Runs: see every run of this flow and what each step did" onClick={() => setShowHistory(true)} disabled={!activeFlow}>
            <History className="w-4 h-4" />
            <span className="hidden min-[1440px]:inline">Runs</span>
          </Button>
          <Button
            variant="outline"
            size="sm"
            className={hit}
            data-testid="flow-settings"
            aria-label="Settings"
            title={canManage ? 'Settings: name, description and category' : 'Settings: see the name, description and category'}
            onClick={() => setShowSettings(true)}
            disabled={!activeFlow}
          >
            <Settings className="w-4 h-4" />
            <span className="hidden min-[1440px]:inline">Settings</span>
          </Button>
        </>
      )}

      {/* Run: always labelled. A draft's run is a test: nothing is turned on. */}
      <DisabledReason reason={canManage ? null : readOnlyReason}>
        <Button
          variant={isPhone ? 'default' : 'outline'}
          size="sm"
          className={hit}
          data-testid="flow-run"
          aria-label={isPhone && !isPublished ? 'Run test' : 'Run'}
          title="Run now: starts the flow once with the input you choose"
          onClick={header.handleRun}
          disabled={!activeFlow || !canManage}
        >
          <Play className="w-4 h-4" />
          {isPhone && !isPublished ? 'Run test' : 'Run'}
        </Button>
      </DisabledReason>

      {/* Publish / Unpublish: always labelled */}
      {activeFlow && !isCompact && (
        <span data-testid={isPublished ? 'flow-published-badge' : 'flow-draft-badge'} className="inline-flex">
          <StatusPill kind={statusKind} data-testid="flow-status-pill" title={isPublished ? 'Live: the trigger is on' : 'Draft: the trigger is off until you publish'} />
        </span>
      )}
      <DisabledReason reason={!canManage ? readOnlyReason : isPublished ? null : publishBlocked}>{publishButton}</DisabledReason>

      {isCompact && (
        <HeaderOverflowMenu
          statusKind={statusKind}
          canManage={canManage}
          readOnlyReason={readOnlyReason}
          hasSteps={(activeFlow?.nodes.length ?? 0) > 1}
          convertedProcedure={convertedProcedure}
          onOpenRuns={() => setShowHistory(true)}
          onOpenSettings={() => setShowSettings(true)}
          onTidy={tidyLayout}
          onConvert={() => setShowConvert(true)}
          editTools={!isPhone}
          extra={isPhone ? phoneView.menuItem : undefined}
        />
      )}

      {activeFlow && (
        <PublishFlowDialog
          open={header.showPublish}
          onOpenChange={header.setShowPublish}
          flowId={activeFlow.id}
          flowName={activeFlow.name}
          trigger={activeFlow.nodes.find((n) => n.data.nodeType === 'trigger')?.data.triggerConfig}
          steps={activeFlow.nodes}
          problems={issues.map((i) => ({ title: i.nodeLabel, message: i.message }))}
          publishing={header.isPublishing}
          onConfirm={() => void header.confirmPublish()}
        />
      )}
      <UnpublishFlowDialog
        open={header.showUnpublish}
        onOpenChange={header.setShowUnpublish}
        flowName={activeFlow?.name ?? ''}
        trigger={activeFlow?.nodes.find((n) => n.data.nodeType === 'trigger')?.data.triggerConfig}
        busy={header.isUnpublishing}
        onConfirm={() => void header.handleUnpublish()}
      />

      {activeFlow && (
        <FlowRunHistory flowId={activeFlow.id} open={showHistory} onOpenChange={setShowHistory} onSelectRun={setSelectedRunId} />
      )}
      <FlowRunViewer
        runId={selectedRunId}
        onClose={() => setSelectedRunId(null)}
        onBack={activeFlow ? () => { setSelectedRunId(null); setShowHistory(true); } : undefined}
      />
      <RunFlowDialog
        open={header.showRunDialog}
        flowId={activeFlow?.id ?? null}
        flowName={activeFlow?.name}
        onOpenChange={header.setShowRunDialog}
        onRun={header.startRun}
      />
      <FlowSettingsModal open={showSettings} onClose={handleCloseSettings} />
      {activeFlow && isCompact && !isPhone && (
        <ConvertToProcedureDialog flowId={activeFlow.id} open={showConvert} onOpenChange={setShowConvert} />
      )}
    </div>
  );
}
