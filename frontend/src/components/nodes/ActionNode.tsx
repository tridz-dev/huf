import { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import {
  Play,
  Repeat,
  GitBranch,
  RotateCw,
  UserCheck,
  Code,
  Mail,
  Webhook,
  FileText,
  Calendar,
  Plus
} from 'lucide-react';
import { FlowNodeData } from '../../types/flow.types';
import { Card } from '../ui/card';
import { Button } from '../ui/button';

const iconMap: Record<string, any> = {
  Play,
  Repeat,
  GitBranch,
  RotateCw,
  UserCheck,
  Code,
  Mail,
  Webhook,
  FileText,
  Calendar
};

interface ActionNodeProps extends NodeProps<FlowNodeData> {
  onAddNode?: (sourceNodeId: string) => void;
}

export const ActionNode = memo(({ id, data, selected, onAddNode }: ActionNodeProps) => {
  const Icon = data.icon && iconMap[data.icon] ? iconMap[data.icon] : Play;

  return (
    <div className="relative group">
      <Handle
        type="target"
        position={Position.Top}
        className="w-3 h-3 !bg-primary border-2 border-white"
      />
      <Card
        className={`w-64 p-4 transition-all duration-200 ${
          selected ? 'ring-2 ring-primary shadow-lg' : 'shadow-md hover:shadow-lg'
        } border-border bg-card`}
      >
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center text-primary">
            <Icon className="w-5 h-5" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-card-foreground truncate">
              {data.label}
            </div>
            {data.description && (
              <div className="text-xs text-muted-foreground">{data.description}</div>
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

ActionNode.displayName = 'ActionNode';
