import { useEffect, useState } from 'react';
import { Play, History, Upload, Loader2, Save, CheckCircle2, Circle, Settings } from 'lucide-react';
import { Button } from './ui/button';
import { useFlowContext } from '../contexts/FlowContext';
import { runFlow, updateFlowDefinitionFields } from '../services/flowApi';
import { toast } from 'sonner';
import { FlowRunHistory } from './FlowRunHistory';
import { FlowRunViewer } from './FlowRunViewer';
import { FlowSettingsModal } from './modals/FlowSettingsModal';
import { useLocation, useNavigate } from 'react-router-dom';

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
      toast.success('Flow run started', { description: `Run ID: ${result.flow_run_id}` });
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
      {/* Save State Indicator */}
      {activeFlow && (
        <div className="flex items-center gap-1.5 mr-2 text-sm text-muted-foreground bg-muted/50 px-2 py-1 rounded-md">
          {saveState === 'saving' ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : saveState === 'error' ? (
            <Circle className="w-3.5 h-3.5 text-destructive" />
          ) : hasUnsavedChanges ? (
            <Circle className="w-3.5 h-3.5 text-orange-400 fill-orange-400" />
          ) : (
            <CheckCircle2 className="w-3.5 h-3.5 text-green-500" />
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
        variant="ghost"
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
        variant="ghost"
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
        variant="ghost"
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
        variant="secondary"
        size="sm"
        className="gap-2 bg-indigo-50 text-indigo-700 hover:bg-indigo-100 dark:bg-indigo-950/50 dark:text-indigo-300 dark:hover:bg-indigo-900/50 border border-indigo-200 dark:border-indigo-800"
        onClick={handleRun}
        disabled={!activeFlow || isRunning}
      >
        {isRunning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
        <span>Run</span>
      </Button>

      {/* Publish Button */}
      <Button
        variant="default"
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
