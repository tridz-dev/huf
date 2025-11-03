import { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { CheckCircle2 } from 'lucide-react';
import { FlowNodeData } from '../../types/flow.types';
import { Card } from '../ui/card';

export const EndNode = memo(({ data, selected }: NodeProps<FlowNodeData>) => {
  return (
    <div>
      <Handle
        type="target"
        position={Position.Top}
        className="w-3 h-3 !bg-green-500 border-2 border-white"
      />
      <Card
        className={`w-64 p-4 transition-all duration-200 ${
          selected ? 'ring-2 ring-green-500 shadow-lg' : 'shadow-md hover:shadow-lg'
        } border-green-500 bg-green-50`}
      >
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center text-green-600">
            <CheckCircle2 className="w-5 h-5" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-green-900 truncate">{data.label}</div>
            {data.description && (
              <div className="text-xs text-green-700">{data.description}</div>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
});

EndNode.displayName = 'EndNode';
