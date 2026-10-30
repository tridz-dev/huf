import { useState } from 'react';
import { useFlowContext } from '@/contexts/FlowContext';
import { runFlow } from '@/services/flowApi';
import { publishedToast, startSummary } from '@/lib/flow-list/flowPublishSummary';
import { toast } from '@/lib/toast';
import { humanizeFlowError, validateFlow } from '@/lib/flow-graph/flowValidation';
import { setChecklistOpen } from '../frame/frameStore';
import { reportFlowRun } from '@/lib/flow-run/flowRunToast';
import type { RunMode } from '@/lib/flow-run/flowRunPayload';

/**
 * What the editor header's buttons do (save, run, publish, unpublish) and the state they need. One place, so the full header,
 * the "..." menu and the phone header all behave the same: nothing is saved or started without the same checks.
 */
export function useFlowHeaderActions() {
  const { activeFlow, hasUnsavedChanges, saveFlow, setFlowPublished, getFlow } = useFlowContext();
  const [showRunDialog, setShowRunDialog] = useState(false);
  const [isPublishing, setIsPublishing] = useState(false);
  const [showPublish, setShowPublish] = useState(false);
  const [showUnpublish, setShowUnpublish] = useState(false);
  const [isUnpublishing, setIsUnpublishing] = useState(false);

  /**
   * Running and publishing need a finished flow. When it is not, open the list of what is left (each row has a Fix button)
   * instead of failing quietly or with a toast. Saving is never blocked, except for a live flow, which its triggers start
   * from what is stored and so has to stay finished.
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

  const startRun = async (payload: Record<string, unknown>, mode: RunMode) => {
    if (!activeFlow) return;
    try {
      reportFlowRun(await runFlow(activeFlow.id, payload, mode), mode);
    } catch (err) {
      toast.error('Could not run the flow', { description: humanizeFlowError(err) });
    }
  };

  const handleSaveDraft = async () => {
    if (activeFlow?.status === 'active' && needsFinishing()) return;
    try {
      await saveFlow();
      toast.success('Flow saved');
    } catch (err) {
      toast.error('Could not save the flow', { description: humanizeFlowError(err) });
    }
  };

  /** Check and save, then show what will start the flow and ask before it goes live. */
  const handlePublish = async () => {
    if (!activeFlow || needsFinishing()) return;
    if (!(await saveIfNeeded('publishing'))) return;
    setShowPublish(true);
  };

  const confirmPublish = async () => {
    if (!activeFlow) return;
    setIsPublishing(true);
    try {
      await setFlowPublished(activeFlow.id, true);
      const trigger = activeFlow.nodes.find((n) => n.data.nodeType === 'trigger')?.data.triggerConfig;
      const toastText = publishedToast(startSummary(trigger, activeFlow.id, window.location.origin));
      toast.success(toastText.title, { description: toastText.description });
      setShowPublish(false);
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
    showRunDialog, setShowRunDialog, isPublishing, showPublish, setShowPublish, confirmPublish, showUnpublish, setShowUnpublish, isUnpublishing,
    handleRun, startRun, handleSaveDraft, handlePublish, handleUnpublish,
  };
}
