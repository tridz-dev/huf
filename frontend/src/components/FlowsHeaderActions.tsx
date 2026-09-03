import { useEffect, useState, type KeyboardEvent } from 'react';
import { Play, History, Upload, Loader2, Save, CheckCircle2, Circle, Settings, Pencil } from 'lucide-react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { useFlowContext } from '../contexts/FlowContext';
import { runFlow, updateFlowDefinitionFields } from '../services/flowApi';
import { toast } from 'sonner';
import { FlowRunHistory } from './FlowRunHistory';
import { FlowRunViewer } from './FlowRunViewer';
import { FlowSettingsModal } from './modals/FlowSettingsModal';

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
  const { activeFlow, saveState, hasUnsavedChanges, saveFlow } = useFlowContext();
  const [isRunning, setIsRunning] = useState(false);
  const [isPublishing, setIsPublishing] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    const sp = new URLSearchParams(location.search);
    const runFromUrl = sp.get('run');
    if (runFromUrl) {
      setSelectedRunId(runFromUrl);
    }
  }, [location.search]);

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

  const handleRun = async () => {
    if (!activeFlow) return;

    // Auto-save if there are unsaved changes
    if (hasUnsavedChanges) {
      try {
        await saveFlow();
      } catch (err) {
        toast.error('Failed to save before running', { description: err instanceof Error ? err.message : 'Unknown error' });
        return;
      }
    }

    setIsRunning(true);
    try {
      const result = await runFlow(activeFlow.id);
      // run_flow executes the flow SYNCHRONOUSLY and returns its final status,
      // so a resolved promise does not mean the run succeeded. Reporting
      // "Flow run started" unconditionally told users a run was fine when it
      // had already failed; surface the real outcome instead.
      if (result.status === 'Failed') {
        toast.error('Flow run failed', {
          description: `Run ID: ${result.flow_run_id} — open Runs for the error`,
        });
      } else if (result.status && result.status.startsWith('Waiting')) {
        toast.info('Flow run is waiting', {
          description: `${result.status} — Run ID: ${result.flow_run_id}`,
        });
      } else {
        toast.success('Flow run started', { description: `Run ID: ${result.flow_run_id}` });
      }
    } catch (err) {
      toast.error('Failed to run flow', { description: err instanceof Error ? err.message : 'Unknown error' });
    } finally {
      setIsRunning(false);
    }
  };

  const handleSaveDraft = async () => {
    try {
      await saveFlow();
      toast.success('Flow saved');
    } catch (err) {
      toast.error('Failed to save', { description: err instanceof Error ? err.message : 'Unknown error' });
    }
  };

  const handlePublish = async () => {
    if (!activeFlow) return;

    // Auto-save if there are unsaved changes
    if (hasUnsavedChanges) {
      try {
        await saveFlow();
      } catch (err) {
        toast.error('Failed to save before publishing', { description: err instanceof Error ? err.message : 'Unknown error' });
        return;
      }
    }

    setIsPublishing(true);
    try {
      // Mark as Active
      await updateFlowDefinitionFields(activeFlow.id, { status: 'Active' });
      toast.success('Flow published successfully');
    } catch (err) {
      toast.error('Failed to publish flow', { description: err instanceof Error ? err.message : 'Unknown error' });
    } finally {
      setIsPublishing(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      {/* Save State Indicator (bare dot + text, no chip background) */}
      {activeFlow && (
        <div className="flex items-center gap-1.5 mr-2 text-muted-foreground">
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

      {/* Save Draft Button */}
      <Button
        variant="outline"
        size="sm"
        className="gap-2"
        onClick={handleSaveDraft}
        disabled={!activeFlow || saveState === 'saving' || !hasUnsavedChanges}
      >
        <Save className="w-4 h-4" />
        <span>Save</span>
      </Button>

      {/* Runs Button */}
      <Button
        variant="outline"
        size="sm"
        className="gap-2"
        onClick={() => setShowHistory(true)}
        disabled={!activeFlow}
      >
        <History className="w-4 h-4" />
        <span>Runs</span>
      </Button>

      {/* Settings Button */}
      <Button
        variant="outline"
        size="sm"
        className="gap-2"
        onClick={() => setShowSettings(true)}
        disabled={!activeFlow}
      >
        <Settings className="w-4 h-4" />
        <span>Settings</span>
      </Button>

      {/* Run Button */}
      <Button
        variant="outline"
        size="sm"
        className="gap-2"
        onClick={handleRun}
        disabled={!activeFlow || isRunning}
      >
        {isRunning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
        <span>Run</span>
      </Button>

      {/* Publish Button */}
      <Button
        variant="display"
        size="sm"
        className="gap-2"
        onClick={handlePublish}
        disabled={!activeFlow || isPublishing}
      >
        {isPublishing ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <Upload className="w-4 h-4" />
        )}
        <span>Publish</span>
      </Button>

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
      <FlowSettingsModal
        open={showSettings}
        onClose={handleCloseSettings}
      />
    </div>
  );
}
