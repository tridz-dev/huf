import { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { CheckCircle2, Trash2 } from 'lucide-react';
import { FlowNodeData } from '../../types/flow.types';
import { Card } from '../ui/card';
import { Button } from '../ui/button';
import { useFlowContext } from '../../contexts/FlowContext';
import { NODE_CARD_BASE, NODE_ICON_WELL } from './nodeStyles';
import { cn } from '@/lib/utils';

export const EndNode = memo(({ id, data, selected }: NodeProps<FlowNodeData>) => {
  const { deleteNode } = useFlowContext();
  return (
    <div className="relative">
      <Handle
        type="target"
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
        {selected && (
          <Button
            variant="ghost"
            size="icon"
            className="absolute top-2 right-2 h-7 w-7 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
            onClick={(e) => {
              e.stopPropagation();
              deleteNode(id);
            }}
            title="Delete node"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </Button>
        )}
        <div className="flex items-center gap-3 pr-6">
          <div className={cn(NODE_ICON_WELL, 'text-good')}>
            <CheckCircle2 className="w-5 h-5" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-foreground truncate">{data.label}</div>
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
