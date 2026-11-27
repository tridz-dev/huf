// @vitest-environment jsdom
import { cleanup, fireEvent, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/contexts/FlowContext', async () => (await import('./formTestKit')).contextMock());
vi.mock('@/hooks/flow/useFlowPermissions', async () => (await import('./formTestKit')).permissionsMock());
vi.mock('@/services/flow/catalogApi', async () => (await import('./formTestKit')).catalogMock());

import { SplitForm } from '../steps/SplitForm';
import { flow, latest, renderForm, updateEdges } from './formTestKit';
import { splitProblems } from '@/lib/flow/splitConfig';
import { validateNode } from '@/lib/flow-graph/flowValidation';
import { actionOptions, ACTION_CARD_CONTRACT } from '@/data/actions';
import { defaultActionConfig } from '@/lib/flow-history/actionDefaults';
import { isPathRouter } from '@/lib/flow/flowBranches';

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
Element.prototype.scrollIntoView ??= () => {};
afterEach(cleanup);

const arm = (id: string, target: string, label: string, weight?: number) => ({
  id, source: 'step', target, sourceHandle: 'option', label, data: { route: 'option', weight },
});

describe('split palette and rules', () => {
  it('is offered in the palette and starts with no holdout', () => {
    expect(actionOptions.find((a) => a.id === 'split')).toMatchObject({ name: 'Split audience', category: 'control' });
    expect(ACTION_CARD_CONTRACT.split).toEqual({ configType: 'split', backendType: 'split' });
    expect(defaultActionConfig('split')).toEqual({ type: 'split', holdout: 0 });
    expect(isPathRouter('split')).toBe(true);
  });

  it('checks branches, shares, holdout and salt', () => {
    const m = (b: Array<{ label?: unknown; weight?: unknown }>, h?: unknown, s?: unknown) => splitProblems(b, h, s).map((p) => p.message);
    expect(m([{ label: 'A', weight: 70 }, { label: 'B', weight: 30 }], 10, 'v1')).toEqual([]);
    expect(m([{ label: 'A', weight: 100 }])).toEqual(['Add at least two branches.']);
    expect(m([{ label: 'A', weight: 60 }, { label: 'B', weight: 30 }])).toEqual(['The branch shares must add up to 100.']);
    expect(m([{ label: 'A', weight: 120 }, { label: '', weight: -20 }])).toEqual(['Give every branch a name.', 'Every branch needs a share from 0 to 100.']);
    expect(m([{ label: 'A', weight: 50 }, { label: 'a', weight: 50 }])).toEqual(['Give each branch a different name.']);
    expect(m([{ label: 'A', weight: 50 }, { label: 'B', weight: 50 }], 101)).toEqual(['The holdout must be a number from 0 to 100.']);
    expect(m([{ label: 'A', weight: 50 }, { label: 'B', weight: 50 }], 0, 'x'.repeat(141))).toEqual(['Keep the salt under 140 characters.']);
  });

  it('flags a split on the canvas until its shares add up', () => {
    const node = { id: 'step', data: { label: 'Split', nodeType: 'action', actionConfig: { type: 'split', holdout: 0 } } };
    const msgs = (edges: Parameters<typeof validateNode>[1]) => validateNode(node, edges).map((i) => i.message);
    expect(msgs([arm('a', 'x', 'A', 50), arm('b', 'y', 'B', 40)])).toEqual(['The branch shares must add up to 100.']);
    expect(msgs([arm('a', 'x', 'A', 50), arm('b', 'y', 'B', 50)])).toEqual([]);
  });
});

describe('SplitForm', () => {
  beforeEach(() => {
    updateEdges.mockClear();
    flow.edges.length = 0;
  });

  it('asks for branches when there are none', async () => {
    renderForm(SplitForm, { type: 'split', holdout: 0 });
    expect(await screen.findByTestId('flow-split-empty')).toBeTruthy();
    expect(screen.getByTestId('flow-split-problem').textContent).toBe('Add at least two branches.');
  });

  it('shows the running total and warns when it is not 100', async () => {
    flow.edges.push(arm('a', 'end', 'A', 70), arm('b', 'end', 'B', 20));
    renderForm(SplitForm, { type: 'split', holdout: 0 });
    expect((await screen.findByTestId('flow-split-total')).textContent).toBe('Total 90% of 100%');
    expect(screen.getByTestId('flow-split-problem').textContent).toBe('The branch shares must add up to 100.');
  });

  it('edits a share on its edge', async () => {
    flow.edges.push(arm('a', 'end', 'A', 70), arm('b', 'end', 'B', 20));
    renderForm(SplitForm, { type: 'split' });
    fireEvent.change(await screen.findByTestId('flow-split-weight-1'), { target: { value: '30' } });
    const next = updateEdges.mock.calls[0][0] as Array<{ id: string; data?: { weight?: number } }>;
    expect(next.find((e) => e.id === 'b')?.data?.weight).toBe(30);
  });

  it('adds a branch with the remaining share', async () => {
    flow.edges.push(arm('a', 'end', 'A', 70));
    renderForm(SplitForm, { type: 'split' });
    fireEvent.click(await screen.findByTestId('flow-split-add'));
    const next = updateEdges.mock.calls[0][0] as Array<{ source: string; label?: string; data?: { route: string; weight?: number } }>;
    const added = next[next.length - 1];
    expect(added.data).toEqual({ route: 'option', weight: 30 });
    expect(added.label).toBe('Branch B');
  });

  it('sets the holdout and salt and flags a bad holdout', async () => {
    flow.edges.push(arm('a', 'end', 'A', 50), arm('b', 'end', 'B', 50));
    renderForm(SplitForm, { type: 'split' });
    fireEvent.change(await screen.findByTestId('flow-field-test-holdout'), { target: { value: '150' } });
    expect(latest.holdout).toBe(150);
    expect(screen.getByTestId('flow-split-holdout-problem').textContent).toBe('The holdout must be a number from 0 to 100.');
    fireEvent.change(screen.getByTestId('flow-field-test-salt'), { target: { value: 'spring' } });
    expect(latest.salt).toBe('spring');
    fireEvent.change(screen.getByTestId('flow-field-test-salt'), { target: { value: ' ' } });
    expect('salt' in latest).toBe(false);
  });
});
