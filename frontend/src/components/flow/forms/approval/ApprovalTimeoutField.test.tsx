// @vitest-environment jsdom
import { useState } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/contexts/FlowContext', async () => (await import('../__tests__/formTestKit')).contextMock());

import { ApprovalTimeoutField } from './ApprovalTimeoutField';
import { flow, updateEdges } from '../__tests__/formTestKit';

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
Element.prototype.scrollIntoView ??= () => {};
Element.prototype.hasPointerCapture ??= () => false;
afterEach(cleanup);
beforeEach(() => updateEdges.mockClear());

let stored: number | undefined;
function Harness({ initial }: { initial?: number }) {
  const [ms, setMs] = useState<number | undefined>(initial);
  stored = ms;
  return <ApprovalTimeoutField nodeId="step" kind="human.approval" timeoutMs={ms} onChange={(v) => { stored = v; setMs(v); }} />;
}
const open = (initial?: number) => {
  stored = initial;
  return render(<Harness initial={initial} />);
};
const amount = () => screen.getByTestId('flow-field-human.approval-timeout_ms') as HTMLInputElement;

describe('ApprovalTimeoutField', () => {
  it('is in minutes, hours or days, and says what happens at the end', () => {
    open(5400000);
    expect(amount().value).toBe('90');
    expect(screen.getByTestId('flow-field-human.approval-timeout_ms-unit').textContent).toContain('minutes');
    expect(screen.getByTestId('flow-hint-approval-timeout').textContent).toContain('After 90 minutes');
    fireEvent.change(amount(), { target: { value: '2' } });
    expect(stored).toBe(120000);
  });

  it('with nothing set it explains that a Timed out path appears once a time is set', () => {
    open();
    expect(amount().value).toBe('');
    expect(screen.getByTestId('flow-hint-approval-timeout').textContent).toContain('a "Timed out" path appears');
  });

  it('explains the "No limit" placeholder: empty means waiting until someone answers', () => {
    open();
    expect(amount().placeholder).toBe('No limit');
    expect(screen.getByTestId('flow-hint-approval-timeout').textContent).toContain('Leave empty to wait until someone answers');
  });

  it('clearing the limit removes the Timed out connection, after asking when something is connected', async () => {
    flow.edges.push({ id: 't1', source: 'step', target: 'end', sourceHandle: 'timeout', data: { route: 'timeout' } });
    open(60000);
    fireEvent.change(amount(), { target: { value: '' } });
    expect(stored).toBe(60000);
    fireEvent.click(await screen.findByTestId('flow-approval-timeout-clear'));
    expect(stored).toBeUndefined();
    const keep = updateEdges.mock.calls.at(-1)?.[0] as Array<{ id: string }>;
    expect(keep.some((e) => e.id === 't1')).toBe(false);
    flow.edges.pop();
  });

  it('keeping the limit puts the number back and leaves the path alone', async () => {
    flow.edges.push({ id: 't1', source: 'step', target: 'end', sourceHandle: 'timeout', data: { route: 'timeout' } });
    open(60000);
    fireEvent.change(amount(), { target: { value: '' } });
    fireEvent.click(await screen.findByTestId('flow-approval-timeout-keep'));
    await waitFor(() => expect(amount().value).toBe('1'));
    expect(stored).toBe(60000);
    expect(updateEdges).not.toHaveBeenCalled();
    flow.edges.pop();
  });

  it('clearing with nothing connected needs no question', () => {
    open(60000);
    fireEvent.change(amount(), { target: { value: '' } });
    expect(stored).toBeUndefined();
    expect(updateEdges).not.toHaveBeenCalled();
  });
});
