import { useEffect, useMemo, useState } from 'react';
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
import { Label } from '../ui/label';
import { RadioGroup, RadioGroupItem } from '../ui/radio-group';
import { useFlowContext } from '../../contexts/FlowContext';
import { outgoingEdges, removeStep, type RemoveStepMode } from '../../lib/flowEdit';

interface DeleteStepDialogProps {
  nodeId: string | null;
  onOpenChange: (open: boolean) => void;
}

/**
 * Confirms removing a step. A step with something after it asks how to treat the rest of the path:
 * reconnect around it (the default) or remove everything that only it led to.
 */
export function DeleteStepDialog({ nodeId, onOpenChange }: DeleteStepDialogProps) {
  const { activeFlow, deleteNode } = useFlowContext();
  const [mode, setMode] = useState<RemoveStepMode>('reconnect');
  const node = nodeId ? activeFlow?.nodes.find((n) => n.id === nodeId) : undefined;
  const followers = useMemo(() => (nodeId && activeFlow ? outgoingEdges(activeFlow.edges, nodeId) : []), [nodeId, activeFlow]);
  const afterCount = useMemo(() => {
    if (!nodeId || !activeFlow) return 0;
    const out = removeStep({ nodes: activeFlow.nodes, edges: activeFlow.edges }, nodeId, 'cascade');
    return activeFlow.nodes.length - out.nodes.length - 1;
  }, [nodeId, activeFlow]);

  useEffect(() => {
    if (nodeId) setMode('reconnect');
  }, [nodeId]);

  const isMiddle = followers.length > 0;
  const bridgeable = followers.length === 1;

  return (
    <AlertDialog open={nodeId !== null} onOpenChange={onOpenChange}>
      <AlertDialogContent onClick={(e) => e.stopPropagation()} data-testid="flow-node-delete-dialog">
        <AlertDialogHeader>
          <AlertDialogTitle>Delete "{node?.data.label ?? 'this step'}"?</AlertDialogTitle>
          <AlertDialogDescription>
            Its settings and connections will be removed. You can undo this right after.
          </AlertDialogDescription>
        </AlertDialogHeader>
        {isMiddle && (
          <RadioGroup value={mode} onValueChange={(v) => setMode(v as RemoveStepMode)} className="gap-3" data-testid="flow-delete-mode">
            <div className="flex items-start gap-2">
              <RadioGroupItem value="reconnect" id="flow-delete-reconnect" data-testid="flow-delete-mode-reconnect" className="mt-0.5" />
              <Label htmlFor="flow-delete-reconnect" className="grid gap-0.5 font-normal">
                <span className="font-medium">{bridgeable ? 'Remove step and reconnect' : 'Remove step only'}</span>
                <span className="text-sm text-muted-foreground">
                  {bridgeable
                    ? 'The step before it connects straight to the step after it.'
                    : 'The steps after it stay on the canvas, but are not connected until you connect them again.'}
                </span>
              </Label>
            </div>
            <div className="flex items-start gap-2">
              <RadioGroupItem value="cascade" id="flow-delete-cascade" data-testid="flow-delete-mode-cascade" className="mt-0.5" />
              <Label htmlFor="flow-delete-cascade" className="grid gap-0.5 font-normal">
                <span className="font-medium">Remove step and everything after it</span>
                <span className="text-sm text-muted-foreground">
                  {afterCount > 0
                    ? `Also removes the ${afterCount} step${afterCount === 1 ? '' : 's'} that can only be reached through it.`
                    : 'The steps after it are also reached from elsewhere, so they stay.'}
                </span>
              </Label>
            </div>
          </RadioGroup>
        )}
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            data-testid="flow-node-delete-confirm"
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            onClick={() => {
              if (nodeId) deleteNode(nodeId, mode);
              onOpenChange(false);
            }}
          >
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
