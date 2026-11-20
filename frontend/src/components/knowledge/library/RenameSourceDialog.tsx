import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';

interface Props {
  open: boolean;
  initial: string;
  busy: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (name: string) => void;
}

export function RenameSourceDialog({ open, initial, busy, onOpenChange, onSave }: Props) {
  const [value, setValue] = useState(initial);
  useEffect(() => setValue(initial), [initial, open]);
  const valid = value.trim().length > 0 && value.trim() !== initial;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Rename knowledge source</DialogTitle></DialogHeader>
        <Input value={value} onChange={(e) => setValue(e.target.value)} aria-label="New name" />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
          <Button onClick={() => onSave(value.trim())} disabled={!valid || busy}>{busy ? 'Saving...' : 'Rename'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
