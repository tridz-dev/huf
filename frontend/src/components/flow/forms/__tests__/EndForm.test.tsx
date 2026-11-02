// @vitest-environment jsdom
import { useState } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/contexts/FlowContext', async () => (await import('./formTestKit')).contextMock());
vi.mock('@/hooks/flow/useFlowPermissions', async () => (await import('./formTestKit')).permissionsMock());
vi.mock('@/services/flow/catalogApi', async () => (await import('./formTestKit')).catalogMock());

import { EndForm } from '../EndForm';
import { updateNodeData } from './formTestKit';
import { deserializeFlow, serializeFlow } from '@/services/flowSerializer';
import type { EndConfig, FlowNode, FlowNodeData } from '@/types/flow.types';

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
Element.prototype.scrollIntoView ??= () => {};
afterEach(cleanup);

let saved: EndConfig = {};

function Harness({ initial }: { initial: EndConfig }) {
  const [node, setNode] = useState<FlowNode>({ id: 'end', type: 'end', position: { x: 0, y: 0 }, data: { label: 'End', nodeType: 'end', icon: 'flag', endConfig: initial } as FlowNodeData });
  updateNodeData.mockImplementation((_id: string, fn: (d: FlowNodeData) => FlowNodeData) => {
    const next = fn(node.data);
    saved = next.endConfig ?? {};
    setNode({ ...node, data: next });
  });
  return <EndForm node={node} />;
}
const open = (initial: EndConfig = {}) => {
  saved = initial;
  return render(<Harness initial={initial} />);
};
const type = (el: HTMLElement, text: string) => {
  el.textContent = text;
  fireEvent.input(el);
};

describe('EndForm', () => {
  it('shows what the run will read as: Finished, neutral, until an outcome is set', async () => {
    open();
    expect((await screen.findByTestId('flow-end-preview-headline')).textContent).toBe('Finished');
    expect(screen.getByTestId('flow-end-preview-chip').getAttribute('data-tone')).toBe('neutral');
    expect(screen.getByText('Run finished', { exact: false })).toBeTruthy();
  });

  it('the outcome wording and the tone change the headline and its colour', async () => {
    open();
    type(await screen.findByTestId('flow-field-output-outcome-label'), 'Refund sent');
    expect(saved.outcome).toEqual({ label: 'Refund sent' });
    fireEvent.click(screen.getByTestId('flow-end-tone-good'));
    expect(saved.outcome).toEqual({ label: 'Refund sent', tone: 'good' });
    expect(screen.getByTestId('flow-end-preview-headline').textContent).toBe('Refund sent');
    expect(screen.getByTestId('flow-end-preview-chip').getAttribute('data-tone')).toBe('good');
    expect(screen.getByTestId('flow-end-tone-good').getAttribute('aria-checked')).toBe('true');
  });

  it('a tone alone is an outcome called Finished; going back to neutral with no words removes it', async () => {
    open();
    fireEvent.click(await screen.findByTestId('flow-end-tone-bad'));
    expect(saved.outcome).toEqual({ tone: 'bad' });
    expect(screen.getByTestId('flow-end-preview-headline').textContent).toBe('Finished');
    fireEvent.click(screen.getByTestId('flow-end-tone-neutral'));
    expect(saved.outcome).toBeUndefined();
  });

  it('data in the outcome reads with its example in the preview', async () => {
    open({ outcome: { label: 'Refunded {input.customer.name}', tone: 'good' } });
    await waitFor(() => expect(screen.getByTestId('flow-end-preview-headline').textContent).toBe('Refunded Ada Lovelace'));
  });

  it('the result stays available, folded away, and opens when it has a value', async () => {
    open({ value: 'done' });
    expect((await screen.findByTestId('flow-more-options-end')).dataset.state).toBe('open');
    cleanup();
    open();
    expect((await screen.findByTestId('flow-more-options-end')).dataset.state).toBe('closed');
  });
});

describe('End outcome in the saved flow', () => {
  const flow = (endConfig: EndConfig) => ({
    id: 'f', name: 'F', status: 'draft' as const, version: 1, createdAt: new Date(), updatedAt: new Date(),
    nodes: [
      { id: 'start', type: 'trigger', position: { x: 0, y: 0 }, data: { label: 'T', nodeType: 'trigger', icon: 'webhook', triggerConfig: { type: 'webhook', method: 'POST', secret: 'x'.repeat(32) } } },
      { id: 'end', type: 'end', position: { x: 0, y: 100 }, data: { label: 'End', nodeType: 'end', icon: 'flag', endConfig } },
    ],
    edges: [{ id: 'e', source: 'start', target: 'end' }],
  }) as never;

  it('is written to the End step and read back', () => {
    const graph = serializeFlow(flow({ value: null as never, outcome: { label: 'Rejected', tone: 'bad' } }));
    const end = graph.nodes.find((n) => n.id === 'end');
    expect(end?.config.outcome).toEqual({ label: 'Rejected', tone: 'bad' });
    const back = deserializeFlow('f', 'F', 'Draft', graph);
    expect(back.nodes.find((n) => n.id === 'end')?.data.endConfig?.outcome).toEqual({ label: 'Rejected', tone: 'bad' });
  });

  it('an empty outcome is not written', () => {
    const graph = serializeFlow(flow({ outcome: { label: '  ' } }));
    expect(graph.nodes.find((n) => n.id === 'end')?.config).not.toHaveProperty('outcome');
  });
});
