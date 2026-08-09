import { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { Plus } from 'lucide-react';
import { Card } from '../ui/card';
import { NODE_CARD_BASE, NODE_ICON_WELL, NODE_HANDLE } from './nodeStyles';
import { cn } from '@/lib/utils';

export interface AddStepGhostNodeData {
  /** The node id that a newly added action should be attached after. */
  sourceNodeId: string;
  onAddNode?: (sourceNodeId: string) => void;
}

/**
 * Persistent, always-visible placeholder card rendered at the end of the
 * node chain. Replaces the old hover-only circular "+" buttons — clicking
 * it opens the same NodeSelectionModal used to add an action node.
 */
export const AddStepGhostNode = memo(({ data }: NodeProps<AddStepGhostNodeData>) => {
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
        aria-label="Add step"
        onClick={(e) => {
          e.stopPropagation();
          data.onAddNode?.(data.sourceNodeId);
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            data.onAddNode?.(data.sourceNodeId);
          }
        }}
        className={cn(
          NODE_CARD_BASE,
          'border-dashed border-line bg-panel/40 shadow-none cursor-pointer hover:border-steel-soft hover:bg-panel/60 transition-colors'
        )}
      >
        <div className="flex items-center gap-3">
          <div className={cn(NODE_ICON_WELL, 'border border-dashed border-line bg-transparent text-muted-foreground')}>
            <Plus className="w-4 h-4" />
          </div>
          <div className="text-sm font-medium text-muted-foreground">Add step</div>
        </div>
      </Card>
    </div>
  );
});

AddStepGhostNode.displayName = 'AddStepGhostNode';
