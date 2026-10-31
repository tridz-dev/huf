// @vitest-environment jsdom
import * as React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render } from '@testing-library/react';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSub, DropdownMenuSubContent, DropdownMenuSubTrigger, DropdownMenuTrigger,
} from './dropdown-menu';

const wait = (ms = 30) => act(async () => { await new Promise((r) => setTimeout(r, ms)); });

function Harness({ onOpenChange }: { onOpenChange?: (o: boolean) => void }) {
  const [open, setOpen] = React.useState(true);
  return (
    <div>
      <button data-testid="before">before</button>
      <DropdownMenu open={open} onOpenChange={(o) => { setOpen(o); onOpenChange?.(o); }} modal={false}>
        <DropdownMenuTrigger data-testid="trigger">open</DropdownMenuTrigger>
        <DropdownMenuContent data-testid="content">
          <DropdownMenuItem>one</DropdownMenuItem>
          <DropdownMenuSub>
            <DropdownMenuSubTrigger>more</DropdownMenuSubTrigger>
            <DropdownMenuSubContent data-testid="sub"><DropdownMenuItem data-testid="subitem">deep</DropdownMenuItem></DropdownMenuSubContent>
          </DropdownMenuSub>
        </DropdownMenuContent>
      </DropdownMenu>
      <button data-testid="after">after</button>
    </div>
  );
}

beforeEach(() => {
  // jsdom has no layout: say every element is on screen.
  vi.spyOn(HTMLElement.prototype, 'getClientRects').mockImplementation(() => [{}] as unknown as DOMRectList);
});
afterEach(() => vi.restoreAllMocks());

describe('Tab in a dropdown menu (ux41)', () => {
  it('Tab closes the menu and puts focus on the next tabbable item after the trigger', async () => {
    const { getByTestId } = render(<Harness />);
    await wait();
    fireEvent.keyDown(document.querySelector('[data-testid="content"]')!, { key: 'Tab' });
    await wait(60);
    expect(document.querySelector('[data-testid="content"]')).toBeNull();
    expect(document.activeElement).toBe(getByTestId('after'));
  });

  it('Shift+Tab puts focus on the previous tabbable item', async () => {
    const { getByTestId } = render(<Harness />);
    await wait();
    fireEvent.keyDown(document.querySelector('[data-testid="content"]')!, { key: 'Tab', shiftKey: true });
    await wait(60);
    expect(document.activeElement).toBe(getByTestId('before'));
  });

  it('Tab inside a submenu closes the whole menu through the open state (no Escape sent)', async () => {
    const changes: boolean[] = [];
    const keys: string[] = [];
    document.addEventListener('keydown', (e) => keys.push(e.key), true);
    render(<Harness onOpenChange={(o) => changes.push(o)} />);
    await wait();
    const sub = document.querySelector<HTMLElement>('[role="menuitem"][aria-haspopup]')!;
    await act(async () => { sub.focus(); fireEvent.keyDown(sub, { key: 'ArrowRight' }); });
    await wait(60);
    const inner = document.querySelector('[data-testid="sub"]');
    expect(inner).not.toBeNull();
    keys.length = 0;
    fireEvent.keyDown(inner!, { key: 'Tab' });
    await wait(60);
    expect(changes).toContain(false);
    expect(document.querySelector('[data-testid="content"]')).toBeNull();
    expect(document.querySelector('[data-testid="sub"]')).toBeNull();
    expect(keys).toEqual(['Tab']);
  });
});
