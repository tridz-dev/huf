import { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { AlertCircle, Zap, Webhook, Clock, Database, Mail, Plus, Trash2, Loader2, CheckCircle2, XCircle } from 'lucide-react';
import { FlowNodeData } from '../../types/flow.types';
import { Card } from '../ui/card';
import { Button } from '../ui/button';
import { useFlowContext } from '../../contexts/FlowContext';

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
  const { deleteNode } = useFlowContext();
  const Icon = data.icon && iconMap[data.icon] ? iconMap[data.icon] : Zap;

  // Determine border/glow based on execution status
  let statusClasses = 'shadow-md hover:shadow-lg';
  if (data.status === 'running') {
    statusClasses = 'ring-2 ring-primary border-primary shadow-lg ring-offset-2 ring-offset-background animate-pulse';
  } else if (data.status === 'success') {
    statusClasses = 'border-green-500 shadow-lg';
  } else if (data.status === 'error') {
    statusClasses = 'border-destructive ring-1 ring-destructive shadow-lg';
  } else if (data.status === 'waiting') {
    statusClasses = 'border-amber-500 ring-1 ring-amber-500 shadow-lg';
  } else if (selected) {
    statusClasses = 'ring-2 ring-primary shadow-lg';
  } else if (!data.configured) {
    statusClasses = 'border-amber-500 bg-amber-50 hover:shadow-lg';
  } else {
    statusClasses = 'border-primary bg-primary/5 hover:shadow-lg';
  }

  return (
    <div className="group relative">
      <Card
        className={`w-64 p-4 transition-all duration-200 ${statusClasses}`}
      >
        {selected && data.status !== 'running' && data.status !== 'waiting' && (
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
          <div
            className={`w-10 h-10 rounded-lg flex items-center justify-center relative ${data.status === 'running' || data.status === 'success' || data.configured
              ? 'bg-primary/10 text-primary'
              : 'bg-amber-100 text-amber-600'
              }`}
          >
            {data.status === 'running' ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : data.status === 'success' ? (
              <CheckCircle2 className="w-5 h-5 text-green-500" />
            ) : data.status === 'error' ? (
              <XCircle className="w-5 h-5 text-destructive" />
            ) : data.status === 'waiting' ? (
              <Clock className="w-5 h-5 text-amber-500" />
            ) : (
              <Icon className="w-5 h-5" />
            )}
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
          onClick={(e) => {
            e.stopPropagation();
            onAddNode?.(id);
          }}
        >
          <Plus className="w-4 h-4" />
        </Button>
      </div>
    </div>
  );
});

TriggerNode.displayName = 'TriggerNode';
