import { memo } from 'react';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { Handle, Position, NodeProps } from 'reactflow';
import { FlowNodeData } from '../../types/flow.types';
import { useFlowContext } from '../../contexts/FlowContext';
import { cn } from '@/lib/utils';
import { unreachableNodeIds } from '../../lib/flow/flowEdit';
import { cardStatus, END_SUBTITLE } from '../../lib/flow/flowNodeCard';
import { cardIcon } from './nodeIcons';
import { CardStatusLine, NodeCard } from './NodeCard';

/** An end step: same card as every other step, marked "End" and outlined in green so it is never mistaken for a middle step. */
export const EndNode = memo(({ id, data, selected }: NodeProps<FlowNodeData>) => {
  const { deleteNode, activeFlow } = useFlowContext();
  const { canManage } = useFlowPermissions();
  const orphaned = activeFlow ? unreachableNodeIds(activeFlow.nodes, activeFlow.edges).has(id) : false;
  const status = cardStatus({ runStatus: data.status, incomplete: false, orphaned, notConnected: false });
  return (
    <div className="relative" data-testid={`flow-node-${id}`} data-node-type="end">
      <Handle
        type="target"
        data-testid={`flow-handle-in-${id}`}
        position={Position.Top}
        className="!bg-good border-2 border-panel w-3 h-3"
      />
      <NodeCard
        id={id}
        icon={cardIcon(data)}
        iconClass="text-good"
        title={data.label}
        subtitle={END_SUBTITLE}
        frameClass={cn('border-good', selected && 'ring-2 ring-signal border-signal')}
        onDelete={
          canManage && selected
            ? (e) => {
                e.stopPropagation();
                deleteNode(id);
              }
            : undefined
        }
        deleteLabel="Delete step"
        footer={<CardStatusLine id={id} status={status} marker={{ text: 'End', testId: `flow-node-marker-${id}` }} />}
      />
    </div>
  );
});

EndNode.displayName = 'EndNode';
