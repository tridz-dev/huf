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

interface DeleteMemoryPolicyDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  policyName: string;
  onConfirm: () => void;
  loading?: boolean;
}

export function DeleteMemoryPolicyDialog({
  open,
  onOpenChange,
  policyName,
  onConfirm,
  loading,
}: DeleteMemoryPolicyDialogProps) {
  return (
    <AlertDialog open={open} onOpenChange={(next) => { if (!loading) onOpenChange(next); }}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete "{policyName}"?</AlertDialogTitle>
          <AlertDialogDescription>
            Agents referencing this memory policy will fall back to no scoped memory
            behavior until a new policy is assigned. This action cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            disabled={loading}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {loading ? 'Deleting...' : 'Delete'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
