import { useEffect, useRef, useState } from 'react';
import { Settings } from 'lucide-react';
import { cn } from '@/lib/utils';
import { DeleteStepDialog } from './flow/DeleteStepDialog';
import { useFlowContext } from '../contexts/FlowContext';
import { EdgeConnectionPanel } from './flow/canvas/EdgeConnectionPanel';
import { StepFrame } from './flow/frame/StepFrame';
import { resetFrame } from './flow/frame/frameStore';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';

interface RightSidebarProps {
  onToggle: () => void;
  variant?: 'panel' | 'sheet';
}

/**
 * The right-hand panel: the open step (see flow/frame/StepFrame: header, status strip, Setup | Test | Settings), the
 * open connection, or a hint when nothing is selected.
 */
export function RightSidebar({ onToggle, variant = 'panel' }: RightSidebarProps) {
  const { activeFlow, selectedNodeId, selectedEdgeId } = useFlowContext();
  const selectedNode = activeFlow?.nodes.find((n) => n.id === selectedNodeId);
  const selectedEdge = activeFlow?.edges.find((e) => e.id === selectedEdgeId);
  const { canManage } = useFlowPermissions();
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const isSheet = variant === 'sheet';

  // Messages already shown, and fields already visited, belong to one flow.
  const flowId = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (flowId.current !== undefined && flowId.current !== activeFlow?.id) resetFrame();
    flowId.current = activeFlow?.id;
  }, [activeFlow?.id]);

  return (
    <div
      data-testid="flow-config-sidebar"
      className={cn('relative bg-card flex flex-col', isSheet ? 'w-full max-w-full' : 'w-[300px] border-l border-border', 'h-full')}
    >
      {!canManage && (selectedNode || selectedEdge) && (
        <div role="status" className="shrink-0 border-b border-border bg-muted px-3.5 py-2 text-xs text-muted-foreground" data-testid="flow-view-only-banner">
          You have view-only access to this flow
        </div>
      )}
      {selectedNode && !selectedEdge ? (
        <StepFrame key={selectedNode.id} node={selectedNode} onClose={isSheet ? undefined : onToggle} onDelete={() => setShowDeleteConfirm(true)} />
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto p-3.5">
          {selectedEdge ? (
            <EdgeConnectionPanel edgeId={selectedEdge.id} />
          ) : (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <Settings className="mb-4 h-12 w-12 text-muted-foreground" />
              <div className="text-sm text-muted-foreground">Select a step or a connection to see its settings</div>
              <p className="mt-2 max-w-[240px] text-xs text-muted-foreground" data-testid="flow-sidebar-empty-hint">
                Click a step on the canvas to set it up. A step marked "Needs setup" still has something missing. Click a line to see what it means.
              </p>
            </div>
          )}
        </div>
      )}
      <DeleteStepDialog nodeId={showDeleteConfirm ? selectedNodeId : null} onOpenChange={setShowDeleteConfirm} />
    </div>
  );
}
