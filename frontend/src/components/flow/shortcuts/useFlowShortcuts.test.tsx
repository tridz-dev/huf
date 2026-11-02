// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import { useFlowShortcuts, type FlowShortcutHandlers } from './useFlowShortcuts';
import { onFlowCommand } from './flowCommands';

const handlers = (): FlowShortcutHandlers => ({ palette: vi.fn(), undo: vi.fn(), redo: vi.fn(), duplicate: vi.fn(), copy: vi.fn(), paste: vi.fn(), selectAll: vi.fn() });

function Harness({ h, enabled = true, canManage = true }: { h: FlowShortcutHandlers; enabled?: boolean; canManage?: boolean }) {
  useFlowShortcuts({ enabled, canManage, handlers: h });
  return (
    <div>
      <input data-testid="field" />
      <button data-testid="btn">x</button>
    </div>
  );
}

const press = (target: Element | Window, init: KeyboardEventInit) => {
  const e = new KeyboardEvent('keydown', { bubbles: true, cancelable: true, ...init });
  (target === window ? document.body : (target as Element)).dispatchEvent(e);
  return e;
};

describe('flow shortcuts', () => {
  beforeEach(() => document.body.replaceChildren());

  it('Cmd and Ctrl both undo; Shift or Y redoes', () => {
    const h = handlers();
    const { getByTestId } = render(<Harness h={h} />);
    const btn = getByTestId('btn');
    press(btn, { key: 'z', ctrlKey: true });
    press(btn, { key: 'z', metaKey: true });
    press(btn, { key: 'Z', metaKey: true, shiftKey: true });
    press(btn, { key: 'y', ctrlKey: true });
    expect(h.undo).toHaveBeenCalledTimes(2);
    expect(h.redo).toHaveBeenCalledTimes(2);
  });

  it('leaves a text field its own undo, copy and paste, but still saves, runs and opens the palette from it', () => {
    const h = handlers();
    const save = vi.fn();
    const run = vi.fn();
    const off = [onFlowCommand('save', save), onFlowCommand('run', run)];
    const { getByTestId } = render(<Harness h={h} />);
    const field = getByTestId('field');
    for (const key of ['z', 'c', 'v', 'd', 'a']) press(field, { key, ctrlKey: true });
    expect(h.undo).not.toHaveBeenCalled();
    expect(h.copy).not.toHaveBeenCalled();
    expect(h.paste).not.toHaveBeenCalled();
    expect(h.duplicate).not.toHaveBeenCalled();
    press(field, { key: 's', metaKey: true });
    press(field, { key: 'Enter', metaKey: true });
    press(field, { key: 'k', metaKey: true });
    expect(save).toHaveBeenCalledTimes(1);
    expect(run).toHaveBeenCalledTimes(1);
    expect(h.palette).toHaveBeenCalledTimes(1);
    off.forEach((f) => f());
  });

  it('takes over the browser keys it uses (Save page, Bookmark) and Cmd+K before the page palette', () => {
    const h = handlers();
    const { getByTestId } = render(<Harness h={h} />);
    const stop = vi.fn();
    window.addEventListener('keydown', stop); // the app-wide palette listens here, after the capture phase
    const k = press(getByTestId('btn'), { key: 'k', metaKey: true });
    expect(k.defaultPrevented).toBe(true);
    expect(stop).not.toHaveBeenCalled();
    const d = press(getByTestId('btn'), { key: 'd', metaKey: true });
    expect(d.defaultPrevented).toBe(true);
    window.removeEventListener('keydown', stop);
  });

  it('does nothing while a dialog is open, on a phone, or without edit rights (except the palette)', () => {
    const h = handlers();
    const view = render(<Harness h={h} canManage={false} />);
    press(view.getByTestId('btn'), { key: 'z', ctrlKey: true });
    press(view.getByTestId('btn'), { key: 'd', ctrlKey: true });
    expect(h.undo).not.toHaveBeenCalled();
    expect(h.duplicate).not.toHaveBeenCalled();
    press(view.getByTestId('btn'), { key: 'k', ctrlKey: true });
    expect(h.palette).toHaveBeenCalledTimes(1);
    view.unmount();

    const h2 = handlers();
    const phone = render(<Harness h={h2} enabled={false} />);
    press(phone.getByTestId('btn'), { key: 'k', ctrlKey: true });
    expect(h2.palette).not.toHaveBeenCalled();
    phone.unmount();

    const h3 = handlers();
    const dialog = document.createElement('div');
    dialog.setAttribute('role', 'dialog');
    dialog.setAttribute('data-state', 'open');
    document.body.appendChild(dialog);
    const withDialog = render(<Harness h={h3} />);
    press(withDialog.getByTestId('btn'), { key: 'z', ctrlKey: true });
    press(withDialog.getByTestId('btn'), { key: 'k', ctrlKey: true });
    expect(h3.undo).not.toHaveBeenCalled();
    expect(h3.palette).not.toHaveBeenCalled();
  });
});
