import { Loader2 } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

/** The one confirmation for deleting a flow, with the same words wherever it is asked. */
export const DELETE_FLOW_TITLE = 'Delete this flow?';
export const DELETE_FLOW_BUTTON = 'Delete flow';

export function deleteFlowMessage(isLive: boolean): string {
  return `This permanently deletes the flow and its run history. You cannot undo it.${isLive ? ' It is live now, so it stops starting by itself.' : ''}`;
}

interface DeleteFlowDialogProps {
  flow: { id: string; name: string; live?: boolean } | null;
  deleting: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export function DeleteFlowDialog({ flow, deleting, onCancel, onConfirm }: DeleteFlowDialogProps) {
  return (
    <AlertDialog open={!!flow} onOpenChange={(open) => !open && !deleting && onCancel()}>
      <AlertDialogContent data-testid="flow-delete-dialog">
        <AlertDialogHeader>
          <AlertDialogTitle>{DELETE_FLOW_TITLE}</AlertDialogTitle>
          <AlertDialogDescription>
            <span className="mb-2 block break-words font-medium text-foreground" title={flow?.name} data-testid="flow-delete-name">
              {flow?.name}
            </span>
            {deleteFlowMessage(!!flow?.live)}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={(e) => {
              e.preventDefault();
              onConfirm();
            }}
            disabled={deleting}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            data-testid="flow-delete-confirm"
          >
            {deleting ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Deleting...
              </>
            ) : (
              DELETE_FLOW_BUTTON
            )}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
