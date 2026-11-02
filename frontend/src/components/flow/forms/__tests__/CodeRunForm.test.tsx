// @vitest-environment jsdom
import { cleanup, fireEvent, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/contexts/FlowContext', async () => (await import('./formTestKit')).contextMock());
vi.mock('@/hooks/flow/useFlowPermissions', async () => (await import('./formTestKit')).permissionsMock());
vi.mock('@/services/flow/catalogApi', async () => (await import('./formTestKit')).catalogMock());
vi.mock('@/lib/flow-graph/useCodeFlowStatus', () => ({
  useCodeFlowStatus: () => ({
    loading: false,
    status: { available: true, default_timeout_s: 30, profiles: [{ name: 'Flow Scratch', approval_mode: 'Auto Approve', max_wall_time_s: 30, usable: true }] },
  }),
}));

import { CodeRunFields } from '../../CodeRunForm';
import { Section } from '../formKit';
import { renderForm, latest } from './formTestKit';

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
Element.prototype.scrollIntoView ??= () => {};
afterEach(cleanup);

const Form = ({ nodeId, cfg, patch, Err }: { nodeId: string; cfg: Record<string, unknown>; patch: (p: Record<string, unknown>) => void; Err: (p: { field: string }) => React.ReactNode }) => (
  <Section title="Execute code">
    <CodeRunFields nodeId={nodeId} cfg={cfg} patch={patch} Err={Err} />
  </Section>
);

describe('Execute code form', () => {
  it('starts with the code, offers an example, and keeps the time limit folded away', () => {
    renderForm(Form as never, { type: 'code-run', profile: 'Flow Scratch', inputs: {} });
    expect(screen.getByTestId('flow-code-editor')).toBeTruthy();
    expect(screen.getByTestId('flow-more-options-code').dataset.state).toBe('closed');
    fireEvent.click(screen.getByTestId('flow-code-example'));
    expect(String(latest.code)).toContain('result =');
    expect(screen.queryByTestId('flow-code-example')).toBeNull();
  });

  it('data for the code is a name and a data box, and a value with data is kept as data', () => {
    renderForm(Form as never, { type: 'code-run', profile: 'Flow Scratch', code: 'x', inputs: { who: { $from: 'input.customer.name' } } });
    expect(screen.getByTestId('flow-code-input-key-0')).toHaveProperty('value', 'who');
    expect(screen.getByTestId('flow-code-input-value-0').querySelector('[data-chip]')).toBeTruthy();
    fireEvent.click(screen.getByTestId('flow-code-inputs-add'));
    expect(Object.keys(latest.inputs as object)).toEqual(['who', 'input_2']);
    expect(document.body.textContent).not.toMatch(/Literal|\$from/);
  });

  it('opens the time limit when one is set', () => {
    renderForm(Form as never, { type: 'code-run', profile: 'Flow Scratch', code: 'x', timeout_s: 10, inputs: {} });
    expect(screen.getByTestId('flow-more-options-code').dataset.state).toBe('open');
    expect((screen.getByTestId('flow-code-timeout') as HTMLInputElement).value).toBe('10');
  });
});
