import { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { Plus } from 'lucide-react';
import { useStore } from 'reactflow';
import { lodForKey, zoomKey, zoomOfKey, counterScale } from '@/lib/flow-canvas/zoomLod';
import { Card } from '../ui/card';
import type { FlowEdgeRoute } from '../../types/flow.types';
import { NODE_CARD_BASE, NODE_ICON_WELL, NODE_HANDLE } from './nodeStyles';
import { cn } from '@/lib/utils';

export interface AddStepGhostNodeData {
  /** The node id that a newly added action should be attached after. */
  sourceNodeId: string;
  /** Which outgoing route of the source this step fills (default: its plain next). */
  route?: FlowEdgeRoute;
  /** Branch name shown on the card, e.g. "True". */
  branchLabel?: string;
  onAddNode?: (sourceNodeId: string, route?: FlowEdgeRoute) => void;
}

/**
 * Persistent, always-visible placeholder card rendered at the end of the
 * node chain. Replaces the old hover-only circular "+" buttons — clicking
 * it opens the same NodeSelectionModal used to add an action node.
 */
export const AddStepGhostNode = memo(({ data }: NodeProps<AddStepGhostNodeData>) => {
  const key = useStore((st) => zoomKey(st.transform[2]));
  const small = lodForKey(key) !== 'full';
  const grow = Math.min(counterScale(zoomOfKey(key)), 2.4);
  return (
    <div className="relative">
      <Handle
        type="target"
        position={Position.Top}
        isConnectable={false}
        className={cn(NODE_HANDLE, 'opacity-0')}
      />
      <Card
        role="button"
        tabIndex={0}
        aria-label={data.branchLabel ? `Add step: ${data.branchLabel}` : 'Add step'}
        title={data.branchLabel ? `Add the step that runs on the "${data.branchLabel}" path` : 'Add the step that runs next'}
        data-testid={`flow-add-step-${data.sourceNodeId}${data.route && data.route !== 'next' ? `-${data.route}` : ''}`}
        onClick={(e) => {
          e.stopPropagation();
          data.onAddNode?.(data.sourceNodeId, data.route);
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            data.onAddNode?.(data.sourceNodeId, data.route);
          }
        }}
        className={cn(
          NODE_CARD_BASE,
          small && 'items-center',
          'h-[72px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal focus-visible:ring-offset-2 border-dashed border-steel-soft bg-panel/40 shadow-none cursor-pointer hover:border-steel-soft hover:bg-panel/60 transition-colors'
        )}
      >
        {small ? (
          <div className={cn(NODE_ICON_WELL, 'border border-dashed border-line bg-transparent text-muted-foreground')} style={{ transform: `scale(${grow})` }}>
            <Plus className="w-4 h-4" />
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <div className={cn(NODE_ICON_WELL, 'border border-dashed border-line bg-transparent text-muted-foreground')}>
              <Plus className="w-4 h-4" />
            </div>
            <div className="text-sm font-medium text-muted-foreground">{data.branchLabel ? `${data.branchLabel}: add step` : 'Add step'}</div>
          </div>
        )}
      </Card>
    </div>
  );
});

AddStepGhostNode.displayName = 'AddStepGhostNode';
