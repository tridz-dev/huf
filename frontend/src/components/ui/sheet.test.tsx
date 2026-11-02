// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { Sheet, SheetContent, SheetTitle, SheetDescription } from './sheet';

function Probe() {
  const [open, setOpen] = useState(true);
  return (
    <>
      <button data-testid="close" onClick={() => setOpen(false)}>close</button>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent data-testid="sheet"><SheetTitle>Runs</SheetTitle><SheetDescription>x</SheetDescription></SheetContent>
      </Sheet>
    </>
  );
}

describe('ux41: a closed sheet releases the page at once (a real browser swallowed clicks for 250 ms while it slid out)', () => {
  it('has no exit animation and unmounts on close', async () => {
    render(<Probe />);
    const content = screen.getByTestId('sheet');
    const overlay = document.querySelector('.bg-black\\/80') as HTMLElement;
    expect(content.className).not.toMatch(/animate-out|slide-out/);
    expect(overlay.className).not.toMatch(/animate-out/);
    expect(content.className).toMatch(/motion-reduce:!animate-none/);
    await act(async () => { (document.querySelector('[data-testid="close"]') as HTMLElement).click(); });
    expect(screen.queryByTestId('sheet')).toBeNull();
    expect(document.body.style.pointerEvents).not.toBe('none');
  });
});
