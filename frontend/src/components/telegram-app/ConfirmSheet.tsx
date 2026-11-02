import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet';

interface Props {
  open: boolean;
  title: string;
  description: string;
  busy: boolean;
  destructive?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Bottom sheet that shows what act_prepare says will happen, before act_confirm. */
export function ConfirmSheet({ open, title, description, busy, destructive, onConfirm, onCancel }: Props) {
  return (
    <Sheet open={open} onOpenChange={(o) => { if (!o && !busy) onCancel(); }}>
      <SheetContent side="bottom" className="rounded-t-xl">
        <SheetHeader>
          <SheetTitle>{title}</SheetTitle>
          <SheetDescription className="whitespace-pre-wrap break-words">{description}</SheetDescription>
        </SheetHeader>
        <SheetFooter className="mt-4 gap-2">
          <Button variant="outline" onClick={onCancel} disabled={busy}>Cancel</Button>
          <Button variant={destructive ? 'destructive' : 'default'} onClick={onConfirm} disabled={busy}>
            {busy ? 'Working...' : 'Confirm'}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
