import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { joinTitles } from './templateModel';

export type SharedAction = 'edit' | 'delete';

interface Props {
  open: boolean;
  action: SharedAction;
  usedBy: { solution: string; title: string }[];
  onConfirm: () => void;
  /** Only offered for edits: opens the create flow prefilled with a new version. */
  onCopy: () => void;
  onCancel: () => void;
}

export function SharedTemplateDialog({ open, action, usedBy, onConfirm, onCopy, onCancel }: Props) {
  const deleting = action === 'delete';
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onCancel()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>This template is shared</DialogTitle>
          <DialogDescription>
            {deleting
              ? `Used by ${joinTitles(usedBy)}. Deleting it removes it for all of them.`
              : `Used by ${joinTitles(usedBy)}. Editing resubmits it to Meta for all of them and pauses sends until it is approved again.`}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2 sm:gap-2">
          <Button onClick={onConfirm}>{deleting ? 'Delete for everyone' : 'Edit for everyone'}</Button>
          {!deleting && <Button variant="outline" onClick={onCopy}>Make a copy</Button>}
          <Button variant="ghost" onClick={onCancel}>Cancel</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
