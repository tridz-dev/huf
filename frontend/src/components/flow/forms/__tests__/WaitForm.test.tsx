// @vitest-environment jsdom
import { cleanup, fireEvent, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/contexts/FlowContext', async () => (await import('./formTestKit')).contextMock());
vi.mock('@/hooks/flow/useFlowPermissions', async () => (await import('./formTestKit')).permissionsMock());
vi.mock('@/services/flow/catalogApi', async () => (await import('./formTestKit')).catalogMock());

import { WaitForm } from '../steps/WaitForm';
import { renderForm, latest } from './formTestKit';

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
Element.prototype.scrollIntoView ??= () => {};
Element.prototype.hasPointerCapture ??= () => false;
afterEach(cleanup);

const mode = (m: string) => screen.getByTestId(`flow-field-test-mode-${m}`);

describe('Wait form', () => {
  it('starts on "For a while" and writes the amount', () => {
    renderForm(WaitForm, { type: 'wait', mode: 'duration', duration: { unit: 'hours' } });
    expect(mode('duration').getAttribute('aria-checked')).toBe('true');
    fireEvent.change(screen.getByTestId('flow-field-test-duration.value'), { target: { value: '3' } });
    expect(latest.duration).toEqual({ unit: 'hours', value: 3 });
    fireEvent.change(screen.getByTestId('flow-field-test-duration.value'), { target: { value: '' } });
    expect((latest.duration as { value?: number }).value).toBeUndefined();
  });

  it('switching mode drops the other modes settings', () => {
    renderForm(WaitForm, { type: 'wait', mode: 'duration', duration: { value: 3, unit: 'days' } });
    fireEvent.click(mode('until'));
    expect(latest.mode).toBe('until');
    expect(latest.duration).toBeUndefined();
    expect(screen.getByTestId('flow-field-test-until')).toBeTruthy();
    expect(screen.getByTestId('flow-field-test-time_zone')).toBeTruthy();
    fireEvent.click(mode('resume'));
    expect(latest.mode).toBe('resume');
    expect(screen.getByTestId('flow-wait-resume-info').textContent).toContain('resume link');
    expect(screen.getByTestId('flow-field-wait-timeout_ms')).toBeTruthy();
    expect(screen.getByText('Give up after (optional)')).toBeTruthy();
  });

  it('the give-up time is saved inside resume, in milliseconds (minutes by default), and clearing it removes resume', () => {
    renderForm(WaitForm, { type: 'wait', mode: 'resume' });
    fireEvent.change(screen.getByTestId('flow-field-wait-timeout_ms'), { target: { value: '2' } });
    expect(latest.resume).toEqual({ timeout_ms: 120_000 });
    fireEvent.change(screen.getByTestId('flow-field-wait-timeout_ms'), { target: { value: '' } });
    expect(latest.resume).toBeUndefined();
  });

  it('the resume link text is hidden once "Or when the person replies" is chosen (the two are exclusive)', () => {
    renderForm(WaitForm, { type: 'wait', mode: 'resume', resume: { wait_for: 'member_reply' } });
    expect(screen.queryByTestId('flow-wait-resume-info')).toBeNull();
  });
});
