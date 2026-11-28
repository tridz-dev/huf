// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/contexts/FlowContext', async () => (await import('./formTestKit')).contextMock());
vi.mock('@/hooks/flow/useFlowPermissions', async () => (await import('./formTestKit')).permissionsMock());
vi.mock('@/services/flow/catalogApi', async () => (await import('./formTestKit')).catalogMock());
vi.mock('@/services/flow/triggerApi', () => ({
  listTriggerDoctypes: vi.fn().mockResolvedValue([{ name: 'ToDo', label: 'To-do', group: 'common' }]),
}));
vi.mock('@/services/flowApi', () => ({
  getFlowDefinitions: vi.fn().mockResolvedValue([
    { flow_id: 'f1', flow_name: 'Refunds', status: 'Active' },
    { flow_id: 'onboarding', flow_name: 'Onboarding', status: 'Active' },
  ]),
}));

import { StopForm } from '../steps/StopForm';
import { DocGetForm } from '../data/DocGetForm';
import { DocUpdateForm } from '../data/DocUpdateForm';
import { FlowCallForm } from '../steps/FlowCallForm';
import { RetryPolicy } from '../steps/RetryPolicy';
import { renderForm, latest } from './formTestKit';
import type { ActionFormProps } from '../formKit';

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
Element.prototype.scrollIntoView ??= () => {};
Element.prototype.hasPointerCapture ??= () => false;
afterEach(cleanup);

const t = (field: string) => screen.getByTestId(`flow-field-test-${field}`);

function RetryHarness({ cfg, patch, f, Err }: ActionFormProps) {
  return <RetryPolicy f={f} Err={Err} retry={cfg.retry as never} onChange={(retry) => patch({ retry })} />;
}

describe('Try again if it fails', () => {
  it('is off and collapsed until turned on, then writes a default policy', () => {
    renderForm(RetryHarness, { type: 'tool-call', tool_id: 'http_request' });
    expect(screen.queryByTestId('flow-field-test-retry.attempts')).toBeNull();
    fireEvent.click(screen.getByTestId('flow-retry-section-toggle'));
    fireEvent.click(t('retry.on'));
    expect(latest.retry).toEqual({ attempts: 3, backoff: 'fixed', delay_seconds: 60 });
  });

  it('writes tries and the backoff, and Longest wait shows only for Longer each time', () => {
    renderForm(RetryHarness, { type: 'tool-call', retry: { attempts: 3, backoff: 'fixed', delay_seconds: 60 } });
    fireEvent.change(t('retry.attempts'), { target: { value: '5' } });
    expect((latest.retry as { attempts: number }).attempts).toBe(5);
    expect(screen.queryByText('Longest wait (optional)')).toBeNull();
    fireEvent.change(t('retry.delay_seconds'), { target: { value: '2' } });
    expect((latest.retry as { delay_seconds: number }).delay_seconds).toBe(120);
  });

  it('turning it off removes the policy', () => {
    renderForm(RetryHarness, { type: 'tool-call', retry: { attempts: 3, backoff: 'fixed', delay_seconds: 60 } });
    fireEvent.click(t('retry.on'));
    expect(latest.retry).toBeUndefined();
  });
});

describe('Stop with error form', () => {
  it('shows its hint and writes the message', () => {
    renderForm(StopForm, { type: 'stop', message: '' });
    expect(screen.getByText('Message')).toBeTruthy();
    expect(screen.getByTestId('flow-hint-stop-message').textContent).toContain('Steps after this one never run');
  });
});

describe('Find document form', () => {
  it('switches between Name and Matching fields, dropping the other', async () => {
    renderForm(DocGetForm, { type: 'doc-get', doctype: 'ToDo', name: 'T-1' });
    expect(t('name')).toBeTruthy();
    fireEvent.click(t('by'));
    fireEvent.click(await screen.findByText('Matching fields'));
    expect(latest.filters).toEqual({});
    expect(latest.name).toBeUndefined();
    expect(t('filters')).toBeTruthy();
  });

  it('writes fields to return as a list and clears it when empty', () => {
    renderForm(DocGetForm, { type: 'doc-get', doctype: 'ToDo', name: 'T-1' });
    fireEvent.change(t('fields'), { target: { value: 'status, owner' } });
    expect(latest.fields).toEqual(['status', 'owner']);
    fireEvent.change(t('fields'), { target: { value: '' } });
    expect(latest.fields).toBeUndefined();
  });
});

describe('Update document form', () => {
  it('shows the field rows and the saved-as hint', () => {
    renderForm(DocUpdateForm, { type: 'doc-update', doctype: 'ToDo', name: 'T-1', values: { status: 'Closed' } });
    expect(t('values')).toBeTruthy();
    expect((screen.getByTestId('flow-field-test-values-key-0') as HTMLInputElement).value).toBe('status');
    fireEvent.click(screen.getByTestId('flow-field-test-values-add'));
    expect(screen.getByTestId('flow-field-test-values-key-1')).toBeTruthy();
  });
});

describe('Run another flow form', () => {
  it('lists published flows except this one and writes the choice', async () => {
    renderForm(FlowCallForm, { type: 'flow-call', flow_id: '' });
    await waitFor(() => expect((t('flow_id') as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(t('flow_id'));
    expect(await screen.findByText('Onboarding')).toBeTruthy();
    expect(screen.queryByText('Refunds')).toBeNull();
    fireEvent.click(screen.getByText('Onboarding'));
    expect(latest.flow_id).toBe('onboarding');
  });

  it('the wait switch sets the mode and shows its hint', () => {
    renderForm(FlowCallForm, { type: 'flow-call', flow_id: 'onboarding', mode: 'fire_and_forget' });
    expect(screen.queryByTestId('flow-hint-flow-call-wait')).toBeNull();
    fireEvent.click(t('mode'));
    expect(latest.mode).toBe('wait');
    expect(screen.getByTestId('flow-hint-flow-call-wait')).toBeTruthy();
  });
});
