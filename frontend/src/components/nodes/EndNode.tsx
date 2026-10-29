import { memo } from 'react';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { Handle, Position, NodeProps } from 'reactflow';
import { CheckCircle2, Trash2 } from 'lucide-react';
import { FlowNodeData } from '../../types/flow.types';
import { Card } from '../ui/card';
import { Button } from '../ui/button';
import { useFlowContext } from '../../contexts/FlowContext';
import { NODE_CARD_BASE, NODE_ICON_WELL } from './nodeStyles';
import { cn } from '@/lib/utils';
import { unreachableNodeIds } from '../../lib/flow/flowEdit';

export const EndNode = memo(({ id, data, selected }: NodeProps<FlowNodeData>) => {
  const { deleteNode, activeFlow } = useFlowContext();
  const { canManage } = useFlowPermissions();
  const orphaned = activeFlow ? unreachableNodeIds(activeFlow.nodes, activeFlow.edges).has(id) : false;
  return (
    <div className="relative" data-testid={`flow-node-${id}`} data-node-type="end">
      <Handle
        type="target"
        data-testid={`flow-handle-in-${id}`}
        position={Position.Top}
        className="!bg-good border-2 border-panel w-3 h-3"
      />
      <Card
        className={cn(
          NODE_CARD_BASE,
          'border-good',
          selected && 'ring-2 ring-signal border-signal'
        )}
      >
        {canManage && selected && (
          <Button
            variant="ghost"
            size="icon"
            className="absolute top-2 right-2 h-7 w-7 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
            onClick={(e) => {
              e.stopPropagation();
              deleteNode(id);
            }}
            data-testid={`flow-node-delete-${id}`}
            aria-label="Delete step"
            title="Delete step"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </Button>
        )}
        <div className="flex items-center gap-3 pr-6">
          <div className={cn(NODE_ICON_WELL, 'text-good')}>
            <CheckCircle2 className="w-5 h-5" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium min-w-0 text-foreground line-clamp-2 break-words leading-snug" title={data.label} data-testid={`flow-node-title-${id}`}>{data.label}</div>
            {orphaned && (
              <div className="text-xs text-signal-ink" data-testid={`flow-node-orphan-${id}`}>Nothing leads to this step</div>
            )}
            {data.description && (
              <div className="text-xs text-muted-foreground">{data.description}</div>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
});

EndNode.displayName = 'EndNode';
