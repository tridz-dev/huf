// @vitest-environment jsdom
import { cleanup, fireEvent, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/contexts/FlowContext', async () => (await import('./formTestKit')).contextMock());
vi.mock('@/hooks/flow/useFlowPermissions', async () => (await import('./formTestKit')).permissionsMock());
vi.mock('@/services/flow/catalogApi', async () => (await import('./formTestKit')).catalogMock());

import { SwitchForm } from '../steps/SwitchForm';
import { flow, renderForm, updateEdges } from './formTestKit';

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
Element.prototype.scrollIntoView ??= () => {};
afterEach(cleanup);

const rule = (id: string, target: string, label: string, expression = '') => ({
  id, source: 'step', target, sourceHandle: 'option', label, data: { route: 'option', expression },
});

describe('SwitchForm', () => {
  beforeEach(() => {
    updateEdges.mockClear();
    flow.edges.length = 0;
  });

  it('asks to add a rule when there are none', async () => {
    renderForm(SwitchForm, { type: 'router-decision' });
    expect(await screen.findByTestId('flow-switch-empty')).toBeTruthy();
    expect(screen.getByText('Otherwise go to')).toBeTruthy();
  });

  it('shows each rule with its name and the rule order controls', async () => {
    flow.edges.push(rule('r1', 'end', 'Urgent', "input['vip'] == True"), rule('r2', 'end', 'Routine'));
    renderForm(SwitchForm, { type: 'router-decision' });
    const name = (await screen.findByTestId('flow-switch-rule-name-end', {}, { timeout: 1000 }).catch(() => null)) as HTMLInputElement | null;
    const inputs = document.querySelectorAll<HTMLInputElement>('[data-testid="flow-switch-rule-name-end"]');
    expect(inputs.length).toBe(2);
    expect(inputs[0].value).toBe('Urgent');
    expect(inputs[1].value).toBe('Routine');
    expect(name === null || name.value === 'Urgent').toBe(true);
    expect(screen.getAllByLabelText('Move rule up').length).toBe(2);
  });

  it('adds a rule to the first step that is not upstream, named after it', async () => {
    flow.nodes.push({ id: 'end', data: { label: 'Done' }, position: { x: 0, y: 0 }, type: 'action' } as never);
    renderForm(SwitchForm, { type: 'router-decision' });
    fireEvent.click(await screen.findByTestId('flow-switch-add-rule'));
    expect(updateEdges).toHaveBeenCalledTimes(1);
    const next = updateEdges.mock.calls[0][0] as Array<{ source: string; target: string; label?: string; data?: { route: string } }>;
    const added = next.find((e) => e.data?.route === 'option');
    expect(added?.source).toBe('step');
    expect(added?.target).toBe('start');
    expect(added?.label).toBeTruthy();
  });

  it('removes a rule by dropping its edge', async () => {
    flow.edges.push(rule('r1', 'end', 'Urgent'));
    renderForm(SwitchForm, { type: 'router-decision' });
    fireEvent.click(await screen.findByTestId('flow-switch-remove-end'));
    expect(updateEdges).toHaveBeenCalledWith([]);
  });
});
