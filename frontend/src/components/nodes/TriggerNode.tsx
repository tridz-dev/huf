import { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { AlertCircle, Zap, Webhook, Clock, Database, Mail, Plus } from 'lucide-react';
import { FlowNodeData } from '../../types/flow.types';
import { Card } from '../ui/card';
import { Button } from '../ui/button';

const iconMap: Record<string, any> = {
  Webhook,
  Clock,
  Database,
  Mail,
  Zap
};

interface TriggerNodeProps extends NodeProps<FlowNodeData> {
  onAddNode?: (sourceNodeId: string) => void;
}

export const TriggerNode = memo(({ id, data, selected, onAddNode }: TriggerNodeProps) => {
  const Icon = data.icon && iconMap[data.icon] ? iconMap[data.icon] : Zap;

  return (
    <div className="group">
      <Card
        className={`w-64 p-4 transition-all duration-200 ${
          selected ? 'ring-2 ring-primary shadow-lg' : 'shadow-md'
        } ${
          data.configured
            ? 'border-primary bg-primary/5 hover:shadow-lg'
            : 'border-amber-500 bg-amber-50 hover:shadow-lg'
        }`}
      >
        <div className="flex items-center gap-3">
          <div
            className={`w-10 h-10 rounded-lg flex items-center justify-center ${
              data.configured
                ? 'bg-primary/10 text-primary'
                : 'bg-amber-100 text-amber-600'
            }`}
          >
            <Icon className="w-5 h-5" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <div className="text-sm font-medium text-card-foreground truncate">
                {data.label}
              </div>
              {!data.configured && (
                <AlertCircle className="w-4 h-4 text-amber-600 flex-shrink-0" />
              )}
            </div>
            {data.description && (
              <div className="text-xs text-muted-foreground">{data.description}</div>
            )}
            {!data.configured && (
              <div className="text-xs text-amber-600 mt-1">Click to configure</div>
            )}
          </div>
        </div>
      </Card>
      <Handle
        type="source"
        position={Position.Bottom}
        className="w-3 h-3 !bg-primary border-2 border-white"
      />
      <div className="absolute -bottom-6 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity">
        <Button
          size="icon"
          className="h-8 w-8 rounded-full shadow-lg"
          onClick={() => onAddNode?.(id)}
        >
          <Plus className="w-4 h-4" />
        </Button>
      </div>
    </div>
  );
});

TriggerNode.displayName = 'TriggerNode';
