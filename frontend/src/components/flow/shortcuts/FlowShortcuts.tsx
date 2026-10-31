import { useCallback, useEffect, useState } from 'react';
import { useStoreApi } from 'reactflow';
import { useFlowContext } from '@/contexts/FlowContext';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { useViewport } from '@/lib/ui/responsive';
import { RENDER_ONLY_NODE_PREFIX } from '@/lib/flow-graph/flowCanvasGraph';
import { pushRecentFlow } from '@/lib/flow-history/recentFlows';
import { FlowCommandPalette } from '../palette/CommandPalette';
import { FlowHelpDialog } from '../FlowHelpPopover';
import { FlowLiveRegion } from './FlowLiveRegion';
import { useFlowCommand } from './flowCommands';
import { useFlowShortcuts } from './useFlowShortcuts';
import { useFlowStepActions } from './useFlowStepActions';

/**
 * Mounted once inside the canvas: the editor's keyboard shortcuts, the Cmd+K palette and the screen-reader announcements.
 * It lives inside the canvas because the steps selected on it (shift-click, box select) are known only there. On a phone the
 * flow is read-only, so none of this exists there.
 */
export function FlowShortcuts() {
  const store = useStoreApi();
  const { isPhone } = useViewport();
  const { canManage } = useFlowPermissions();
  const { undo, redo, selectedNodeId, activeFlowId } = useFlowContext();
  const actions = useFlowStepActions();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);

  useEffect(() => {
    if (activeFlowId) pushRecentFlow(activeFlowId);
  }, [activeFlowId]);

  /** The steps selected on the canvas (a box or shift-click can select several), else the one the panel shows. */
  const getSelectedIds = useCallback((): string[] => {
    const picked = store.getState().getNodes().filter((n) => n.selected && !n.id.startsWith(RENDER_ONLY_NODE_PREFIX)).map((n) => n.id);
    if (picked.length > 0) return picked;
    return selectedNodeId ? [selectedNodeId] : [];
  }, [store, selectedNodeId]);

  const selectAll = useCallback(() => {
    const ids = store.getState().getNodes().filter((n) => !n.id.startsWith(RENDER_ONLY_NODE_PREFIX)).map((n) => n.id);
    store.getState().addSelectedNodes(ids);
  }, [store]);

  useFlowCommand('palette', () => setPaletteOpen(true), !isPhone);

  useFlowShortcuts({
    enabled: !isPhone,
    canManage,
    handlers: {
      palette: () => setPaletteOpen((open) => !open),
      undo,
      redo,
      duplicate: () => void actions.duplicate(getSelectedIds()),
      copy: () => void actions.copy(getSelectedIds()),
      paste: () => void actions.paste(),
      selectAll,
    },
  });

  if (isPhone) return null;
  return (
    <>
      <FlowLiveRegion />
      <FlowCommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} getSelectedIds={getSelectedIds} onOpenHelp={() => setHelpOpen(true)} />
      <FlowHelpDialog open={helpOpen} onOpenChange={setHelpOpen} />
    </>
  );
}
