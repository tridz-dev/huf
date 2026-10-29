import { memo, useState } from 'react';
import { useFlowPermissions } from '@/hooks/useFlowPermissions';
import { Handle, Position, NodeProps } from 'reactflow';
import { Zap, Webhook, Clock, Database, Mail, CircleDashed, Trash2, Loader2, CheckCircle2, XCircle, type LucideIcon } from 'lucide-react';
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
import { NODE_CARD_BASE, NODE_HANDLE, NODE_ICON_WELL, getExecutionStatusClasses } from './nodeStyles';
import { cn } from '@/lib/utils';
import { validateNode } from '../../lib/flowValidation';

const iconMap: Record<string, LucideIcon> = {
  Webhook,
  Clock,
  Database,
  Mail,
  CircleDashed,
  Zap
};

type TriggerNodeProps = NodeProps<FlowNodeData>;

export const TriggerNode = memo(({ id, data, selected }: TriggerNodeProps) => {
  const { deleteNode, activeFlow } = useFlowContext();
  const { canManage } = useFlowPermissions();
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const Icon = data.icon && iconMap[data.icon] ? iconMap[data.icon] : Zap;
  const incomplete = validateNode({ id, data }, activeFlow?.edges ?? []);
  const statusClasses = getExecutionStatusClasses(data.status, selected, {
    unconfigured: incomplete.length > 0 || !data.triggerConfig?.type,
  });

  // A trigger only becomes `configured` after the user saves it in the trigger
  // modal, so the flag is a trustworthy signal here (unlike for actions).
  const handleDeleteClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (data.configured) {
      setShowDeleteConfirm(true);
    } else {
      deleteNode(id);
    }
  };

  return (
    <div className="relative" data-testid={`flow-node-${id}`} data-node-type={data.triggerConfig?.type ?? 'unset'} data-incomplete={incomplete.length > 0 ? 'true' : 'false'}>
      <Card className={cn(NODE_CARD_BASE, statusClasses)}>
        {canManage && selected && data.status !== 'running' && data.status !== 'waiting' && (
          <Button
            variant="ghost"
            size="icon"
            className="absolute top-2 right-2 h-7 w-7 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
            onClick={handleDeleteClick}
            data-testid={`flow-node-delete-${id}`}
            aria-label="Delete trigger"
            title="Delete trigger"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </Button>
        )}
        <div className="flex items-center gap-3 pr-6">
          <div
            className={cn(
              NODE_ICON_WELL,
              data.configured ? 'text-ink' : 'text-signal'
            )}
          >
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
            <div className="flex items-center gap-2">
              <div className="text-sm font-medium min-w-0 text-card-foreground line-clamp-2 break-words leading-snug" title={data.label} data-testid={`flow-node-title-${id}`}>
                {data.label}
              </div>
            </div>
            {data.description && (
              <div className="text-xs text-muted-foreground">{data.description}</div>
            )}
            {incomplete.length > 0 && (
              <div className="text-xs text-signal-ink mt-1" data-testid={`flow-node-incomplete-${id}`}>Needs setup</div>
            )}
          </div>
          <span className="ml-auto flex-shrink-0 rounded border border-line bg-panel/60 font-mono uppercase tracking-wider text-steel font-medium px-1.5 py-0.5 text-[9px]">
            Trigger
          </span>
        </div>
      </Card>
      <Handle
        data-testid={`flow-handle-${id}`}
        type="source"
        position={Position.Bottom}
        className={NODE_HANDLE}
      />

      <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <AlertDialogContent onClick={(e) => e.stopPropagation()} data-testid="flow-node-delete-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Delete "{data.label}"?</AlertDialogTitle>
            <AlertDialogDescription>
              This trigger is configured. Deleting it will permanently remove its settings and any
              edges connected to it. This can't be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              data-testid="flow-node-delete-confirm"
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

TriggerNode.displayName = 'TriggerNode';
