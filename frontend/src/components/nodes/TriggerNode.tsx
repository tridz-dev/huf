import { memo, useState } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { AlertCircle, Zap, Webhook, Clock, Database, Mail, CircleDashed, Trash2, Loader2, CheckCircle2, XCircle, type LucideIcon } from 'lucide-react';
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
  const { deleteNode } = useFlowContext();
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const Icon = data.icon && iconMap[data.icon] ? iconMap[data.icon] : Zap;
  const statusClasses = getExecutionStatusClasses(data.status, selected, {
    unconfigured: !data.configured,
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
    <div className="relative">
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
              <div className="text-sm font-medium text-card-foreground truncate">
                {data.label}
              </div>
              {!data.configured && (
                <AlertCircle className="w-4 h-4 text-signal flex-shrink-0" />
              )}
            </div>
            {data.description && (
              <div className="text-xs text-muted-foreground">{data.description}</div>
            )}
            {!data.configured && (
              <div className="text-xs text-signal-ink mt-1">Click to configure</div>
            )}
          </div>
          <span className="ml-auto flex-shrink-0 rounded border border-line bg-panel/60 font-mono uppercase tracking-wider text-steel-soft font-medium px-1.5 py-0.5 text-[9px]">
            Trigger
          </span>
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
              This trigger is configured. Deleting it will permanently remove its settings and any
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

TriggerNode.displayName = 'TriggerNode';
