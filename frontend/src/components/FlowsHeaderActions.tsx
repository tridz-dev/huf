import { useState } from 'react';
import { Play, History, Upload, Loader2 } from 'lucide-react';
import { Button } from './ui/button';
import { useFlowContext } from '../contexts/FlowContext';
import { runFlow } from '../services/flowApi';
import { serializeFlow } from '../services/flowSerializer';
import { saveFlowDefinition, updateFlowDefinitionFields } from '../services/flowApi';
import { toast } from 'sonner';

export function FlowsHeaderActions() {
  const { activeFlow } = useFlowContext();
  const [isRunning, setIsRunning] = useState(false);
  const [isPublishing, setIsPublishing] = useState(false);

  const handleRun = async () => {
    if (!activeFlow) return;
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

  const handlePublish = async () => {
    if (!activeFlow) return;
    setIsPublishing(true);
    try {
      // Save current graph state
      const graph = serializeFlow(activeFlow);
      await saveFlowDefinition(activeFlow.id, graph);
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
    <>
      <Button
        variant="ghost"
        size="sm"
        className="gap-2"
        onClick={handleRun}
        disabled={!activeFlow || isRunning}
      >
        {isRunning ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <Play className="w-4 h-4" />
        )}
        <span>Run</span>
      </Button>
      <Button variant="ghost" size="sm" className="gap-2">
        <History className="w-4 h-4" />
        <span>Versions</span>
      </Button>
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
    </>
  );
}
