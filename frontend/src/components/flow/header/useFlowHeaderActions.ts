import { useState } from 'react';
import { useFlowContext } from '@/contexts/FlowContext';
import { getFlowIntegrationStatus, runFlow } from '@/services/flowApi';
import { unconnectedSteps } from '@/lib/flow/flowIntegrations';
import { toast } from '@/lib/toast';
import { BLOCKED_TOAST_ID, humanizeFlowError, summarizeIssues, validateFlow } from '@/lib/flow-graph/flowValidation';
import { reportFlowRun } from '@/lib/flow-run/flowRunToast';

/**
 * What the editor header's buttons do (save, run, publish, unpublish) and the state they need. One place, so the full header,
 * the "..." menu and the phone header all behave the same: nothing is saved or started without the same checks.
 */
export function useFlowHeaderActions() {
  const { activeFlow, hasUnsavedChanges, saveFlow, setSelectedNode, setFlowPublished } = useFlowContext();
  const [showRunDialog, setShowRunDialog] = useState(false);
  const [isPublishing, setIsPublishing] = useState(false);
  const [showUnpublish, setShowUnpublish] = useState(false);
  const [isUnpublishing, setIsUnpublishing] = useState(false);

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

  return {
    showRunDialog, setShowRunDialog, isPublishing, showUnpublish, setShowUnpublish, isUnpublishing,
    handleRun, startRun, handleSaveDraft, handlePublish, handleUnpublish,
  };
}
