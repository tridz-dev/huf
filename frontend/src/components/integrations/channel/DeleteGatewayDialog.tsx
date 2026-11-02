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

interface DeleteGatewayDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  gatewayName: string;
  deleting: boolean;
  onConfirm: () => void;
}

export function DeleteGatewayDialog({
  open,
  onOpenChange,
  gatewayName,
  deleting,
  onConfirm,
}: DeleteGatewayDialogProps) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete this gateway?</AlertDialogTitle>
          <AlertDialogDescription>
            This permanently removes the &quot;{gatewayName}&quot; gateway and stops it from
            receiving messages. The connected credentials are not deleted and can be reused by another
            gateway.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            disabled={deleting}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {deleting ? 'Deleting...' : 'Delete'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
