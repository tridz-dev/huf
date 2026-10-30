/**
 * Shared set-up for the step form tests: a small flow (a webhook with an example, the step under test, an End), mocked
 * services and a harness that holds the step's settings the way the sidebar does (`patch` merges, `undefined` removes).
 */
import { type ComponentType, type ReactNode, useState } from 'react';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import type { ActionFormProps, Cfg } from './formKit';

export const ORDER = { customer: { name: 'Ada Lovelace', email: 'ada@example.com' }, total: 450, items: [{ name: 'Tea' }, { name: 'Cake' }] };

export const updateEdges = vi.fn();
export const updateNodeData = vi.fn();

export const flow = {
  id: 'f1',
  name: 'Refunds',
  nodes: [
    { id: 'start', type: 'trigger', position: { x: 0, y: 0 }, data: { label: 'New order', nodeType: 'trigger', icon: 'webhook', triggerConfig: { type: 'webhook' }, sample: ORDER } },
    { id: 'post', type: 'action', position: { x: 0, y: 100 }, data: { label: 'Call a web address', nodeType: 'action', icon: 'globe', actionConfig: { type: 'tool-call', tool_id: 'http_request' } } },
    { id: 'step', type: 'action', position: { x: 0, y: 200 }, data: { label: 'The step', nodeType: 'action', icon: 'x', actionConfig: { type: 'condition' } } },
    { id: 'end', type: 'end', position: { x: 0, y: 300 }, data: { label: 'End', nodeType: 'end', icon: 'flag', endConfig: {} } },
  ],
  edges: [
    { id: 'e1', source: 'start', target: 'post' },
    { id: 'e2', source: 'post', target: 'step' },
    { id: 'e3', source: 'step', target: 'end' },
  ] as Array<Record<string, unknown>>,
};

/** What `vi.mock` hands back for the modules every form reads. */
export const contextMock = () => ({
  useFlowContext: () => ({
    activeFlow: flow,
    updateNodeData,
    updateEdges,
    getNode: (id: string) => flow.nodes.find((n) => n.id === id),
    setSelectedNode: vi.fn(),
  }),
});
export const permissionsMock = (canManage = true) => ({
  useFlowPermissions: () => ({ canManage, canExecuteCode: true }),
});
export const catalogMock = () => ({ getDataCatalog: vi.fn().mockResolvedValue(null) });

export let latest: Cfg = {};

function Harness({ Form, initial }: { Form: ComponentType<ActionFormProps>; initial: Cfg }) {
  const [cfg, setCfg] = useState<Cfg>(initial);
  latest = cfg;
  const patch = (p: Cfg) =>
    setCfg((c) => {
      const next: Cfg = { ...c, ...p };
      for (const k of Object.keys(p)) if (p[k] === undefined) delete next[k];
      latest = next;
      return next;
    });
  const Err = ({ field }: { field: string }): ReactNode => <span data-testid={`err-${field}`} hidden />;
  return <Form nodeId="step" cfg={cfg} patch={patch} f={(field) => `flow-field-test-${field}`} Err={Err} title="Test" />;
}

export function renderForm(Form: ComponentType<ActionFormProps>, initial: Cfg) {
  latest = initial;
  return render(
    <MemoryRouter>
      <Harness Form={Form} initial={initial} />
    </MemoryRouter>
  );
}

/** Types into a data box (a contenteditable) the way the editor sees it. */
export function typeInto(box: HTMLElement, text: string, fire: (el: HTMLElement) => void) {
  box.textContent = text;
  fire(box);
}

export const boxText = (el: HTMLElement) => (el.textContent ?? '').replace(/×/g, '').replace(/\s+/g, ' ').trim();
