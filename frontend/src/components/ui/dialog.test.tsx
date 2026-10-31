// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { toast } from 'sonner';
import { render, screen, act } from '@testing-library/react';
import { useState } from 'react';
import { Dialog, DialogContent, DialogTitle } from './dialog';
import { AlertDialog, AlertDialogContent, AlertDialogTitle, AlertDialogDescription } from './alert-dialog';

function Probe({ initial = true }: { initial?: boolean }) {
  const [open, setOpen] = useState(initial);
  return (
    <>
      <button data-testid="close" onClick={() => setOpen(false)}>close</button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-testid="dlg"><DialogTitle>Settings</DialogTitle></DialogContent>
      </Dialog>
    </>
  );
}

describe('repair-c-01: a closed dialog releases the page at once', () => {
  it('unmounts and leaves body clickable in the same frame as the close', async () => {
    render(<Probe />);
    expect(screen.getByTestId('dlg')).toBeTruthy();
    await act(async () => { (document.querySelector('[data-testid="close"]') as HTMLElement).click(); });
    expect(screen.queryByTestId('dlg')).toBeNull();
    expect(document.body.style.pointerEvents).not.toBe('none');
  });

  it('has no exit animation (a fading overlay would catch clicks and keep body inert)', () => {
    render(<Probe />);
    const content = screen.getByTestId('dlg');
    const overlay = document.querySelector('.bg-black\\/\\[\\.28\\]') as HTMLElement;
    expect(content.className).not.toMatch(/animate-out/);
    expect(overlay.className).not.toMatch(/animate-out/);
    expect(content.className).toMatch(/motion-reduce:!animate-none/);
    expect(overlay.className).toMatch(/motion-reduce:!animate-none/);
  });

  it('final2-04: opening a dialog clears passive toasts but keeps errors and Undo toasts', () => {
    const ok = toast.success('Saved');
    const info = toast.info('Heads up');
    const err = toast.error('Could not save');
    const undo = toast('Deleted', { action: { label: 'Undo', onClick: () => undefined } });
    const dismiss = vi.spyOn(toast, 'dismiss');
    render(<Probe />);
    const gone = dismiss.mock.calls.map((c) => c[0]);
    expect(gone).toContain(ok);
    expect(gone).toContain(info);
    expect(gone).not.toContain(err);
    expect(gone).not.toContain(undo);
    dismiss.mockRestore();
  });

  it('same for the alert dialog', () => {
    render(
      <AlertDialog open>
        <AlertDialogContent data-testid="alert"><AlertDialogTitle>Sure?</AlertDialogTitle><AlertDialogDescription>x</AlertDialogDescription></AlertDialogContent>
      </AlertDialog>,
    );
    expect(screen.getByTestId('alert').className).not.toMatch(/animate-out/);
  });
});
