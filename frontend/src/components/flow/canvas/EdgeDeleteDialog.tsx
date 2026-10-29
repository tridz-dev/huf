import type { Edge, Node } from 'reactflow';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '../../ui/alert-dialog';
import type { FlowNodeData } from '../../../types/flow.types';

/** Asks before a connection is removed (the button on the line and the Delete key both open it). */
export function EdgeDeleteDialog({
  edgeId, nodes, edges, onCancel, onConfirm,
}: {
  edgeId: string | null;
  nodes: Node<FlowNodeData>[];
  edges: Edge[];
  onCancel: () => void;
  onConfirm: (edgeId: string) => void;
}) {
  const edge = edges.find((ed) => ed.id === edgeId);
  const from = nodes.find((n) => n.id === edge?.source)?.data.label ?? 'the step';
  const to = nodes.find((n) => n.id === edge?.target)?.data.label ?? 'the next step';
  return (
    <AlertDialog open={edgeId !== null} onOpenChange={(open) => !open && onCancel()}>
      <AlertDialogContent data-testid="flow-edge-delete-dialog">
        <AlertDialogHeader>
          <AlertDialogTitle>Remove this connection?</AlertDialogTitle>
          <AlertDialogDescription>
            {`"${from}" will no longer lead to "${to}". The steps stay on the canvas; connect them again or delete the one left over. You can undo this right after.`}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            data-testid="flow-edge-delete-confirm"
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            onClick={() => {
              if (edgeId) onConfirm(edgeId);
              onCancel();
            }}
          >
            Remove connection
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
