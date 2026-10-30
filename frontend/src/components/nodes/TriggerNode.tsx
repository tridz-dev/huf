import { memo, useState } from 'react';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { Handle, Position, NodeProps } from 'reactflow';
import { FlowNodeData } from '../../types/flow.types';
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
import { NODE_HANDLE, getExecutionStatusClasses } from './nodeStyles';
import { triggerSubtitle } from '../../lib/flow/flowNodeCard';
import { cardIcon } from './nodeIcons';
import { CardStatusLine, NodeCard } from './NodeCard';

type TriggerNodeProps = NodeProps<FlowNodeData>;

export const TriggerNode = memo(({ id, data, selected }: TriggerNodeProps) => {
  const { canManage } = useFlowPermissions();
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const facts = data.canvas;
  const status = facts?.status ?? { kind: 'ready' as const, text: 'Ready' };
  const needsSetup = status.kind === 'needs-setup' || Boolean(facts?.firstIssue);
  const unset = !data.triggerConfig?.type;
  const statusClasses = getExecutionStatusClasses(data.status, selected, {
    unconfigured: needsSetup || unset,
  });

  // A trigger only becomes `configured` after the user saves it in the trigger
  // modal, so the flag is a trustworthy signal here (unlike for actions).
  const handleDeleteClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (data.configured) {
      setShowDeleteConfirm(true);
    } else {
      facts?.onDelete?.(id);
    }
  };

  const canDelete = canManage && selected && data.status !== 'running' && data.status !== 'waiting';
  return (
    <div className="relative" data-testid={`flow-node-${id}`} data-node-type={data.triggerConfig?.type ?? 'unset'} data-incomplete={needsSetup ? 'true' : 'false'}>
      <NodeCard
        id={id}
        icon={cardIcon(data)}
        iconClass={unset ? 'text-signal' : undefined}
        // The empty trigger is one short line and one button; it never shows the stored placeholder name.
        title={unset ? 'Start here' : data.label}
        subtitle={unset ? undefined : triggerSubtitle(data.triggerConfig)}
        status={status}
        runSummary={data.runSummary}
        frameClass={statusClasses}
        onDelete={canDelete ? handleDeleteClick : undefined}
        deleteLabel="Delete trigger"
        footer={
          unset && canManage ? (
            <Button size="sm" className="mt-1 w-full whitespace-nowrap px-2 text-xs" data-testid={`flow-node-choose-trigger-${id}`}>
              Choose what starts this flow
            </Button>
          ) : (
            <CardStatusLine
              id={id}
              status={status}
              title={status.kind === 'needs-setup' ? facts?.firstIssue ?? 'Select this trigger to set it up' : undefined}
              marker={unset ? undefined : { text: 'Trigger', testId: `flow-node-marker-${id}` }}
            />
          )
        }
      />
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
                facts?.onDelete?.(id);
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
