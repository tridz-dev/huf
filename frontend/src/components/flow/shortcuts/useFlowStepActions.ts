import { useCallback } from 'react';
import { useFlowContext } from '@/contexts/FlowContext';
import { toast } from '@/lib/toast';
import { announce } from '@/lib/flow-history/announce';
import { duplicateSteps } from '@/lib/flow-history/flowDuplicate';
import { buildClipboard, pasteSteps, readClipboard, writeClipboard } from '@/lib/flow-history/flowClipboard';
import { insertSpot, insertStep } from '@/lib/flow-history/insertStep';
import { defaultActionConfig } from '@/lib/flow-history/actionDefaults';

const stepsText = (n: number) => (n === 1 ? 'Step' : `${n} steps`);

/** How many times each copy was already pasted into the open flow, so repeated pastes step along instead of piling up. */
const pasteCounts = new Map<string, number>();

/**
 * Duplicate, copy, paste and add-a-step for the open flow. Each takes the ids it acts on, so the keyboard handler (which reads
 * the canvas selection), the "..." menu of a step (which knows its own step) and the palette can all share them.
 */
export function useFlowStepActions() {
  const { getFlow, updateNodesAndEdges, setSelectedNode, undo, activeFlowId } = useFlowContext();

  const select = useCallback((ids: string[]) => {
    if (ids.length > 0) setSelectedNode(ids[0]);
  }, [setSelectedNode]);

  const duplicate = useCallback((ids: string[]): boolean => {
    const flow = getFlow();
    if (!flow || ids.length === 0) return false;
    const result = duplicateSteps({ nodes: flow.nodes, edges: flow.edges }, ids, Date.now());
    if (!result) return false;
    if (result.addedIds.length === 0) {
      toast.info('A flow has only one trigger', { description: 'The trigger cannot be duplicated.' });
      return false;
    }
    const added = new Set(result.addedIds);
    updateNodesAndEdges(result.nodes.map((n) => ({ ...n, selected: added.has(n.id) })), result.edges);
    select(result.addedIds);
    const text = result.addedIds.length === 1 ? 'Step duplicated' : `${result.addedIds.length} steps duplicated`;
    announce(text);
    toast(text, { id: 'flow-duplicate-toast', duration: 3000, action: { label: 'Undo', onClick: () => undo() } });
    return true;
  }, [getFlow, updateNodesAndEdges, select, undo]);

  const copy = useCallback((ids: string[]): boolean => {
    const flow = getFlow();
    if (!flow || ids.length === 0) return false;
    const payload = buildClipboard({ nodes: flow.nodes, edges: flow.edges }, ids, flow.id, Date.now());
    if (!payload) return false;
    if (!writeClipboard(payload)) {
      toast.error('Could not copy', { description: 'Your browser did not let the editor keep the copy.' });
      return false;
    }
    const text = `${stepsText(payload.nodes.length)} copied`;
    announce(text);
    toast(text, { id: 'flow-copy-toast', duration: 2500, description: 'Paste it here or in another flow. Passwords, keys and saved examples are left out.' });
    return true;
  }, [getFlow]);

  const paste = useCallback((): boolean => {
    const flow = getFlow();
    if (!flow) return false;
    const payload = readClipboard();
    if (!payload) {
      toast.info('Nothing to paste yet', { description: 'Select a step and copy it first.' });
      return false;
    }
    const key = `${flow.id}:${payload.copiedAt}`;
    const count = pasteCounts.get(key) ?? 0;
    const result = pasteSteps(payload, { nodes: flow.nodes, edges: flow.edges }, flow.id, Date.now(), count);
    if (result.addedIds.length === 0) {
      toast.info('Nothing was pasted', { description: result.skippedTrigger ? 'This flow already has a trigger, and a flow has only one.' : undefined });
      return false;
    }
    pasteCounts.set(key, count + 1);
    updateNodesAndEdges(result.nodes, result.edges);
    select(result.addedIds);
    const text = `${stepsText(result.addedIds.length)} pasted`;
    announce(text);
    toast(text, {
      id: 'flow-paste-toast',
      duration: 3500,
      description: result.skippedTrigger ? 'The trigger was left out: this flow already has one.' : 'They are not connected yet. Drag from one step to another to connect them.',
      action: { label: 'Undo', onClick: () => undo() },
    });
    return true;
  }, [getFlow, updateNodesAndEdges, select, undo]);

  /** Add a step of this palette kind behind `afterId` (the selected step) or at the end of the flow. */
  const addStep = useCallback((actionId: string, name: string, afterId: string | null, codeProfile?: string | null): boolean => {
    const flow = getFlow();
    if (!flow) return false;
    const graph = { nodes: flow.nodes, edges: flow.edges };
    const spot = insertSpot(graph, afterId);
    if (!spot) {
      toast.info('Add a trigger first', { description: 'Steps follow the trigger that starts the flow.' });
      return false;
    }
    const result = insertStep(graph, spot, actionId, defaultActionConfig(actionId, codeProfile));
    if (result === 'end-in-front') {
      toast.error('Finish can only end a path', { description: 'Add it at the open end of a path, not in front of another step.' });
      return false;
    }
    if (!result) return false;
    updateNodesAndEdges(result.nodes, result.edges);
    setSelectedNode(result.newId);
    announce(`${name} step added`);
    return true;
  }, [getFlow, updateNodesAndEdges, setSelectedNode]);

  return { duplicate, copy, paste, addStep, activeFlowId };
}
