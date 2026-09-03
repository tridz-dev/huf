import { memo, useState } from 'react';
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
  Plus,
  Bot,
  Wrench,
  Trash2,
  type LucideIcon,
} from 'lucide-react';
import { FlowNodeData } from '../../types/flow.types';
import { Card } from '../ui/card';
import { Button } from '../ui/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '../ui/alert-dialog';
import { useFlowContext } from '../../contexts/FlowContext';
import { Loader2, CheckCircle2, XCircle, Clock } from 'lucide-react';
import { NODE_CARD_BASE, NODE_HANDLE, NODE_ICON_WELL, getExecutionStatusClasses } from './nodeStyles';
import { cn } from '@/lib/utils';

const iconMap: Record<string, LucideIcon> = {
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
  Bot,
  Wrench
};

interface ActionNodeProps extends NodeProps<FlowNodeData> {
  onAddNode?: (sourceNodeId: string) => void;
}

/**
 * Whether this action node's config actually carries user-entered
 * configuration worth protecting from an accidental delete-click.
 *
 * `data.configured` alone isn't a good signal here: NodeSelectionModal
 * stamps `configured: true` the moment an action TYPE is picked, even
 * though every field (agent_name, tool_name, url, ...) is still blank.
 * So a node the user just added by mistake would already read as
 * "configured" and force a confirmation dialog on delete. Instead we
 * look at whether the fields a user would actually fill in have any
 * content.
 */
function actionHasConfiguredContent(data: FlowNodeData): boolean {
  const config = data.actionConfig;
  if (!config || !config.type) return false;

  switch (config.type) {
    case 'agent-run':
      return Boolean(config.agent_name?.trim());
    case 'tool-call':
      return Boolean(config.tool_name?.trim());
    case 'router':
      return Boolean(config.router_agent_name?.trim());
    case 'human.approval':
      return Boolean(
        config.assigned_role?.trim() || (config.assigned_user && config.assigned_user.length > 0)
      );
    case 'condition':
      return Boolean(config.expression?.trim() || config.true_node?.trim() || config.false_node?.trim());
    case 'http-request':
      return Boolean(config.url?.trim());
    case 'transform':
      return Boolean(config.transformations && config.transformations.length > 0);
    case 'loop':
      return Boolean(config.iterate_over?.trim());
    default:
      // Unknown/unhandled action config shape — fall back to the
      // coarse flag rather than silently skipping confirmation.
      return data.configured;
  }
}

export const ActionNode = memo(({ id, data, selected, onAddNode }: ActionNodeProps) => {
  const { deleteNode } = useFlowContext();
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const Icon = data.icon && iconMap[data.icon] ? iconMap[data.icon] : Play;
  const statusClasses = getExecutionStatusClasses(data.status, selected);

  const handleDeleteClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (actionHasConfiguredContent(data)) {
      setShowDeleteConfirm(true);
    } else {
      deleteNode(id);
    }
  };

  return (
    <div className="relative group">
      <Handle
        type="target"
        position={Position.Top}
        className={NODE_HANDLE}
      />
      <Card className={cn(NODE_CARD_BASE, statusClasses)}>
        {selected && data.status !== 'running' && data.status !== 'waiting' && (
          <Button
            variant="ghost"
            size="icon"
            className="absolute top-2 right-2 h-7 w-7 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
            onClick={handleDeleteClick}
            title="Delete node"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </Button>
        )}
        <div className="flex items-center gap-3 pr-6">
          <div className={cn(NODE_ICON_WELL, 'text-ink relative')}>
            {data.status === 'running' ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : data.status === 'success' ? (
              <CheckCircle2 className="w-5 h-5 text-good" />
            ) : data.status === 'error' ? (
              <XCircle className="w-5 h-5 text-destructive" />
            ) : data.status === 'waiting' ? (
              <Clock className="w-5 h-5 text-signal" />
            ) : (
              <Icon className="w-5 h-5" />
            )}
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
        className={NODE_HANDLE}
      />
      <div className="absolute -bottom-6 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity">
        <Button
          variant="default"
          size="icon"
          className="h-8 w-8"
          onClick={(e) => {
            e.stopPropagation();
            onAddNode?.(id);
          }}
        >
          <Plus className="w-4 h-4" />
        </Button>
      </div>

      <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <AlertDialogContent onClick={(e) => e.stopPropagation()}>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete "{data.label}"?</AlertDialogTitle>
            <AlertDialogDescription>
              This node is configured. Deleting it will permanently remove its settings and any
              edges connected to it. This can't be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                deleteNode(id);
                setShowDeleteConfirm(false);
              }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
});

ActionNode.displayName = 'ActionNode';
