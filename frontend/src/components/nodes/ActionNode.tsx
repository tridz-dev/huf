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
  Bot,
  Wrench,
  Trash2,
  Database,
  Save,
  FilePlus,
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
import { actionHasConfiguredContent } from '../../lib/flowNodeConfigured';

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
  Wrench,
  Database,
  Save,
  Trash2,
  FilePlus
};

type ActionNodeProps = NodeProps<FlowNodeData>;

export const ActionNode = memo(({ id, data, selected }: ActionNodeProps) => {
  const { deleteNode } = useFlowContext();
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const Icon = data.icon && iconMap[data.icon] ? iconMap[data.icon] : Play;
  const statusClasses = getExecutionStatusClasses(data.status, selected);

  // Confirm only when the node has real config; a picked-but-blank node deletes
  // immediately (see actionHasConfiguredContent).
  const handleDeleteClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (actionHasConfiguredContent(data)) {
      setShowDeleteConfirm(true);
    } else {
      deleteNode(id);
    }
  };

  return (
    <div className="relative">
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
