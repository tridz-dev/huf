// @vitest-environment jsdom
import * as React from 'react';
import { cleanup, render } from '@testing-library/react';
import { act, fireEvent } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { useClosingGuard, withGuard } from './useClosingGuard';

function Probe({ state, onReady }: { state: 'open' | 'closed'; onReady: (guard: (e: Event) => void) => void }) {
  const { ref, guard } = useClosingGuard<HTMLDivElement>(null);
  React.useEffect(() => { onReady(guard); }, [guard, onReady]);
  return <div ref={ref} data-state={state} data-testid="c" />;
}

// jsdom has no PointerEvent: without one, button and ctrlKey are lost and Radix ignores the press.
if (!('PointerEvent' in window)) (window as unknown as { PointerEvent: typeof MouseEvent }).PointerEvent = class extends MouseEvent {} as typeof MouseEvent;

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const press = () => document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }));

describe('ux31-03: a fading menu ignores outside clicks that began while it was fading', () => {
  it('cancels the dismissal when the click started while the content was closed (fading), even if the click itself opened it again', () => {
    let guard!: (e: Event) => void;
    const view = render(<Probe state="closed" onReady={(g) => (guard = g)} />);
    press();
    // The trigger's handler has re-rendered the content as open by the time the outside check runs.
    view.rerender(<Probe state="open" onReady={(g) => (guard = g)} />);
    const event = new Event('dismissableLayer.pointerDownOutside', { cancelable: true });
    guard(event);
    expect(event.defaultPrevented).toBe(true);
  });

  it('lets an open menu close on an outside click', () => {
    let guard!: (e: Event) => void;
    render(<Probe state="open" onReady={(g) => (guard = g)} />);
    press();
    const event = new Event('dismissableLayer.pointerDownOutside', { cancelable: true });
    guard(event);
    expect(event.defaultPrevented).toBe(false);
  });

  it('runs the caller handler first and respects its preventDefault', () => {
    const seen: string[] = [];
    const handler = withGuard<Event>((e) => seen.push(e.type), () => seen.push('guard'));
    handler(new Event('x', { cancelable: true }));
    expect(seen).toEqual(['x', 'guard']);
  });
});

describe('guard only judges pointer presses', () => {
  it('a focus-outside (Tab) event still dismisses, even right after a press that began while fading', () => {
    let guard!: (e: Event) => void;
    render(<Probe state="closed" onReady={(g) => (guard = g)} />);
    press();
    const focus = new Event('dismissableLayer.focusOutside', { cancelable: true });
    guard(focus);
    expect(focus.defaultPrevented).toBe(false);
  });

  it('forgets the fading press after the click, so the next outside press closes', async () => {
    vi.useFakeTimers();
    try {
      let guard!: (e: Event) => void;
      render(<Probe state="closed" onReady={(g) => (guard = g)} />);
      press();
      document.body.dispatchEvent(new Event('click', { bubbles: true }));
      await vi.advanceTimersByTimeAsync(5);
      const event = new Event('dismissableLayer.pointerDownOutside', { cancelable: true });
      guard(event);
      expect(event.defaultPrevented).toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });
});

// Real Radix dropdown menu (its trigger opens on pointerdown, like the bug). jsdom has no CSS animation, so the fade-out is faked: the content reports an animation name while closed.
function Harness() {
  const [open, setOpen] = React.useState(true);
  return (
    <div>
      <DropdownMenu open={open} onOpenChange={setOpen} modal={false}>
        <DropdownMenuTrigger data-testid="trigger">open</DropdownMenuTrigger>
        <DropdownMenuContent data-testid="content">
          <DropdownMenuItem>inside</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <button data-testid="other">other</button>
    </div>
  );
}

function fakeFade() {
  const real = window.getComputedStyle.bind(window);
  vi.spyOn(window, 'getComputedStyle').mockImplementation((el: Element, pseudo?: string | null) => {
    const style = real(el, pseudo);
    if ((el as HTMLElement).dataset?.testid === 'content') {
      // Presence keeps one style object and reads it again when the state flips, so decide at read time.
      return new Proxy(style, {
        get: (t, k) => (k === 'animationName' ? ((el as HTMLElement).dataset.state === 'closed' ? 'fade-out' : 'none') : Reflect.get(t, k)),
      }) as CSSStyleDeclaration;
    }
    return style;
  });
}

const state = () => document.querySelector<HTMLElement>('[data-testid="content"]')?.dataset.state;

describe('useClosingGuard in a real dropdown menu', () => {
  it('a real outside click closes it', async () => {
    render(<Harness />);
    await act(async () => { await new Promise((r) => setTimeout(r, 10)); }); // Radix arms its outside listener on the next tick
    expect(state()).toBe('open');
    fireEvent.pointerDown(document.body);
    await act(async () => { await new Promise((r) => setTimeout(r, 10)); });
    expect(document.querySelector('[data-testid="content"]')).toBeNull();
  });

  it('Escape closes it', async () => {
    render(<Harness />);
    await act(async () => { await new Promise((r) => setTimeout(r, 10)); }); // Radix arms its outside listener on the next tick
    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' });
    await act(async () => { await new Promise((r) => setTimeout(r, 10)); });
    expect(document.querySelector('[data-testid="content"]')).toBeNull();
  });

  it('the Tab key pressed inside the menu closes it (Radix alone swallows Tab and leaves it open)', async () => {
    render(<Harness />);
    await act(async () => { await new Promise((r) => setTimeout(r, 10)); });
    expect(state()).toBe('open');
    fireEvent.keyDown(document.querySelector('[data-testid="content"]')!, { key: 'Tab' });
    await act(async () => { await new Promise((r) => setTimeout(r, 10)); });
    expect(document.querySelector('[data-testid="content"]')).toBeNull();
  });

  it('Tab out (focus moves outside) closes it, even after an earlier press that began while it was fading', async () => {
    fakeFade();
    render(<Harness />);
    await act(async () => { await new Promise((r) => setTimeout(r, 10)); }); // Radix arms its outside listener on the next tick
    const trigger = document.querySelector<HTMLElement>('[data-testid="trigger"]')!;
    fireEvent.keyDown(document.body, { key: 'Escape' });
    await act(async () => { await new Promise((r) => setTimeout(r, 10)); });
    expect(state()).toBe('closed');
    fireEvent.pointerDown(document.body); // noted while fading; no click follows
    fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false }); // reopen
    await act(async () => { await new Promise((r) => setTimeout(r, 10)); });
    expect(state()).toBe('open');
    const other = document.querySelector<HTMLElement>('[data-testid="other"]')!;
    await act(async () => { other.focus(); await new Promise((r) => setTimeout(r, 10)); });
    expect(state()).not.toBe('open');
  });

  it('a click that reopens it while it is fading out keeps it open', async () => {
    fakeFade();
    render(<Harness />);
    await act(async () => { await new Promise((r) => setTimeout(r, 10)); }); // Radix arms its outside listener on the next tick
    const trigger = document.querySelector<HTMLElement>('[data-testid="trigger"]')!;
    fireEvent.keyDown(document.body, { key: 'Escape' });
    await act(async () => { await new Promise((r) => setTimeout(r, 10)); });
    expect(state()).toBe('closed'); // still mounted: fading
    // The press on the trigger: noted first, then the trigger reopens it, then the outside check runs.
    fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false });
    await act(async () => { await new Promise((r) => setTimeout(r, 10)); });
    expect(state()).toBe('open');
  });
});
