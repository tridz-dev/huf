// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { FlowNode } from '@/types/flow.types';
import type { StepTestInfo, StepTestResult } from '@/services/flow/stepTestApi';

const ctx = vi.hoisted(() => ({
  value: {
    activeFlow: { id: 'flow-1', status: 'draft' as string, nodes: [] as unknown[], edges: [] as unknown[] },
    hasUnsavedChanges: false,
    saveFlow: vi.fn(async () => undefined),
    updateNodeData: vi.fn(),
  },
  canManage: true,
}));
vi.mock('@/contexts/FlowContext', () => ({ useFlowContext: () => ctx.value }));
vi.mock('@/hooks/flow/useFlowPermissions', () => ({ useFlowPermissions: () => ({ canManage: ctx.canManage }) }));
const view = vi.hoisted(() => ({ isPhone: false }));
vi.mock('@/lib/ui/responsive', () => ({ useViewport: () => ({ isPhone: view.isPhone, width: view.isPhone ? 390 : 1440 }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const api = vi.hoisted(() => ({
  getStepTestInfo: vi.fn(),
  testStep: vi.fn(),
  getStepTestResult: vi.fn(),
  isStepTestPending: (value: { status: string }) => value.status === 'running',
  listRecentDocuments: vi.fn(),
  getDocumentSample: vi.fn(),
}));
vi.mock('@/services/flow/stepTestApi', () => api);
vi.mock('@/lib/flow-test/pollStepTest', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/flow-test/pollStepTest')>();
  return { ...actual, pollStepTest: (first: never, options: object) => actual.pollStepTest(first, { ...options, intervalMs: 5, maxMs: 120 }) };
});
const trig = vi.hoisted(() => ({ getLastWebhookRequest: vi.fn() }));
vi.mock('@/services/flow/triggerApi', () => trig);

import { StepTestPanel } from './StepTestPanel';
import { forgetStepResult } from '@/hooks/flow/useStepTest';
import { resetAiConfirmed } from '@/lib/flow-test/testModel';

const node = (data: Partial<FlowNode['data']> = {}, id = 's1'): FlowNode =>
  ({ id, type: 'action', position: { x: 0, y: 0 }, data: { label: 'Send email', nodeType: 'action', configured: true, ...data } }) as FlowNode;

const info = (over: Partial<StepTestInfo> = {}): StepTestInfo => ({
  flow_id: 'flow-1', node_id: 's1', kind: 'tool.call', effect: 'reads', calls_ai: false, simulated: false, approval: false, trigger: false, trigger_kind: null,
  parts: [{ key: 'input', title: 'What the flow starts with', kind: 'input', source: 'last_run', value: { name: 'Ada Lovelace' }, shortened: false, ran_at: null }],
  sample_input: { input: { name: 'Ada Lovelace' }, steps: {} },
  ...over,
});

const result = (over: Partial<StepTestResult> = {}): StepTestResult => ({
  status: 'success', mode: 'real', output: { total: 450 }, output_shortened: false, pin_value: { total: 450 }, duration_ms: 120, error: null, fix_hint: null,
  tested_at: new Date().toISOString(), effect: 'reads', calls_ai: false, summary: null, preview: null, goes_to: null, branch: null, warnings: [], ...over,
});

const open = async (n = node(), over: Partial<StepTestInfo> = {}, active = true) => {
  api.getStepTestInfo.mockResolvedValue(info(over));
  const view = render(<StepTestPanel node={n} active={active} onOpenSetup={onSetup} />);
  await screen.findByTestId('flow-step-test');
  return view;
};
const onSetup = vi.fn();

beforeEach(() => {
  forgetStepResult('flow-1', 's1');
  forgetStepResult('flow-1', 't1');
  vi.clearAllMocks();
  ctx.canManage = true;
  view.isPhone = false;
  ctx.value.hasUnsavedChanges = false;
  ctx.value.activeFlow = { id: 'flow-1', status: 'draft', nodes: [], edges: [] };
  resetAiConfirmed();
});
afterEach(cleanup);

describe('Test tab: a step', () => {
  it('shows the sample input with where it came from, then the result of a test', async () => {
    await open();
    expect(screen.getByTestId('flow-step-test-source-input').textContent).toBe('From last run');
    expect(screen.getByText('Ada Lovelace')).toBeTruthy();
    api.testStep.mockResolvedValue(result());
    fireEvent.click(screen.getByTestId('flow-step-test-run'));
    await screen.findByTestId('flow-step-test-result');
    expect(api.testStep).toHaveBeenCalledWith('flow-1', 's1', undefined);
    expect(screen.getByTestId('flow-step-test-status').textContent).toContain('Succeeded');
    expect(screen.getByTestId('flow-step-test-duration').textContent).toContain('120 ms');
    expect(screen.getByTestId('flow-step-test-output-raw-toggle')).toBeTruthy();
  });

  it('waits for a slow step in the background: a token first, then the answer', async () => {
    await open();
    api.testStep.mockResolvedValue({ status: 'running', token: 't'.repeat(32), poll_after_ms: 1000, wait_up_to_s: 35 });
    api.getStepTestResult
      .mockResolvedValueOnce({ status: 'running', token: 't'.repeat(32), poll_after_ms: 1000, wait_up_to_s: 35 })
      .mockResolvedValue(result({ output: 'Hello from the agent' }));
    fireEvent.click(screen.getByTestId('flow-step-test-run'));
    await screen.findByTestId('flow-step-test-result');
    expect(api.getStepTestResult).toHaveBeenCalledWith('t'.repeat(32));
    expect(api.getStepTestResult.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it('says the background worker is busy when no answer ever comes', async () => {
    await open();
    api.testStep.mockResolvedValue({ status: 'running', token: 'u'.repeat(32), poll_after_ms: 1000, wait_up_to_s: 35 });
    api.getStepTestResult.mockResolvedValue({ status: 'running', token: 'u'.repeat(32), poll_after_ms: 1000, wait_up_to_s: 35 });
    fireEvent.click(screen.getByTestId('flow-step-test-run'));
    await waitFor(() => expect(document.body.textContent).toContain('The background worker is busy: try again'));
  });

  it('stops asking when the person leaves the step', async () => {
    const view2 = await open();
    api.testStep.mockResolvedValue({ status: 'running', token: 'v'.repeat(32), poll_after_ms: 1000, wait_up_to_s: 35 });
    api.getStepTestResult.mockResolvedValue({ status: 'running', token: 'v'.repeat(32), poll_after_ms: 1000, wait_up_to_s: 35 });
    fireEvent.click(screen.getByTestId('flow-step-test-run'));
    await waitFor(() => expect(api.getStepTestResult).toHaveBeenCalled());
    view2?.unmount?.();
    cleanup();
    const calls = api.getStepTestResult.mock.calls.length;
    await new Promise((r) => setTimeout(r, 60));
    expect(api.getStepTestResult.mock.calls.length - calls).toBeLessThanOrEqual(1);
  });

  it('names the button "Test (simulated)" for a step that sends and says nothing is sent', async () => {
    await open(node(), { effect: 'sends', simulated: true });
    expect(screen.getByTestId('flow-step-test-run').textContent).toContain('Test (simulated)');
    expect(screen.getByTestId('flow-step-test-hint').textContent).toContain('Nothing is sent');
    api.testStep.mockResolvedValue(result({ mode: 'simulated', effect: 'sends', summary: 'Would send email to ada@example.com', output: { simulated: true } }));
    fireEvent.click(screen.getByTestId('flow-step-test-run'));
    expect((await screen.findByTestId('flow-step-test-summary')).textContent).toBe('Would send email to ada@example.com');
    expect(screen.getByTestId('flow-step-test-status').textContent).toContain('simulated');
  });

  it('shows a failure in plain words with a fix hint and a way to the Setup tab', async () => {
    await open();
    api.testStep.mockResolvedValue(result({ status: 'failed', output: null, pin_value: null, error: 'Choose which action this step should do, then run again.', fix_hint: 'Finish this step on the Setup tab, then test again.' }));
    fireEvent.click(screen.getByTestId('flow-step-test-run'));
    await screen.findByTestId('flow-step-test-error');
    expect(screen.getByTestId('flow-step-test-status').textContent).toBe('Failed');
    expect(screen.getByTestId('flow-step-test-fix').textContent).toContain('Setup tab');
    expect(screen.queryByTestId('flow-step-pin')).toBeNull();
    fireEvent.click(screen.getByTestId('flow-step-test-open-setup'));
    expect(onSetup).toHaveBeenCalled();
  });

  it('pins the output, then shows when it was pinned with Unpin', async () => {
    const { rerender } = await open();
    api.testStep.mockResolvedValue(result());
    fireEvent.click(screen.getByTestId('flow-step-test-run'));
    fireEvent.click(await screen.findByTestId('flow-step-pin'));
    expect(ctx.value.updateNodeData).toHaveBeenCalledTimes(1);
    const update = ctx.value.updateNodeData.mock.calls[0][1];
    const next = update({ label: 'x', nodeType: 'action', configured: true });
    expect(next.sample).toEqual({ total: 450 });
    expect(typeof next.sampleAt).toBe('string');
    rerender(<StepTestPanel node={node({ sample: { total: 450 }, sampleAt: new Date().toISOString() })} active onOpenSetup={onSetup} />);
    expect(screen.getByTestId('flow-step-pinned').textContent).toContain('Pinned just now');
    fireEvent.click(screen.getByTestId('flow-step-unpin'));
    const cleared = ctx.value.updateNodeData.mock.calls[1][1]({ label: 'x', nodeType: 'action', configured: true, sample: { total: 450 }, sampleAt: 'now' });
    expect(cleared.sample).toBeUndefined();
    expect(cleared.sampleAt).toBeUndefined();
  });

  it('asks once before a step that calls the AI model', async () => {
    await open(node(), { calls_ai: true });
    expect(screen.getByTestId('flow-step-test-ai-note').textContent).toContain('This step calls the AI model');
    api.testStep.mockResolvedValue(result({ calls_ai: true, output: 'Hello' }));
    fireEvent.click(screen.getByTestId('flow-step-test-run'));
    await screen.findByTestId('flow-step-test-ai-confirm');
    expect(api.testStep).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('flow-step-test-ai-confirm-yes'));
    await waitFor(() => expect(api.testStep).toHaveBeenCalledTimes(1));
    await screen.findByTestId('flow-step-test-result');
    fireEvent.click(screen.getByTestId('flow-step-test-run'));
    await waitFor(() => expect(api.testStep).toHaveBeenCalledTimes(2));
    expect(screen.queryByTestId('flow-step-test-ai-confirm')).toBeNull();
  });

  it('lets the author edit the sample and tests with it', async () => {
    await open();
    fireEvent.click(screen.getByTestId('flow-step-test-edit'));
    const box = (await screen.findByTestId('flow-json-step-test-sample-input')) as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: '{"input": {"name": "Grace"}, "steps": {}}' } });
    api.testStep.mockResolvedValue(result());
    fireEvent.click(screen.getByTestId('flow-step-test-run'));
    await screen.findByTestId('flow-step-test-result');
    expect(api.testStep).toHaveBeenCalledWith('flow-1', 's1', { input: { name: 'Grace' }, steps: {} });
  });

  it('does not test with a sample that is not JSON', async () => {
    await open();
    fireEvent.click(screen.getByTestId('flow-step-test-edit'));
    fireEvent.change(await screen.findByTestId('flow-json-step-test-sample-input'), { target: { value: '{oops' } });
    fireEvent.click(screen.getByTestId('flow-step-test-run'));
    expect((await screen.findByTestId('flow-step-test-run-error')).textContent).toContain('not valid JSON');
    expect(api.testStep).not.toHaveBeenCalled();
  });

  it('saves unsaved changes before testing', async () => {
    ctx.value.hasUnsavedChanges = true;
    await open();
    api.testStep.mockResolvedValue(result());
    fireEvent.click(screen.getByTestId('flow-step-test-run'));
    await screen.findByTestId('flow-step-test-result');
    expect(ctx.value.saveFlow).toHaveBeenCalled();
    expect(ctx.value.saveFlow.mock.invocationCallOrder[0]).toBeLessThan(api.testStep.mock.invocationCallOrder[0]);
  });

  it('shows a readable message when the test cannot run (for example the rate limit)', async () => {
    await open();
    api.testStep.mockRejectedValue(new Error('You are testing steps very quickly. Wait a minute, then try again.'));
    fireEvent.click(screen.getByTestId('flow-step-test-run'));
    expect((await screen.findByTestId('flow-step-test-run-error')).textContent).toContain('Wait a minute');
  });

  it('shows the approval card preview', async () => {
    await open(node(), { approval: true });
    api.testStep.mockResolvedValue(result({ mode: 'preview', output: null, pin_value: null, preview: { title: 'Refund for Ada', note: 'Please check', facts: [{ label: 'Amount', value: '450' }], who_can_decide: 'Anyone with the role Manager' } }));
    fireEvent.click(screen.getByTestId('flow-step-test-run'));
    expect((await screen.findByTestId('flow-step-test-approval-title')).textContent).toBe('Refund for Ada');
    expect(screen.getByTestId('flow-step-test-approval-who').textContent).toContain('Manager');
    expect(screen.queryByTestId('flow-step-pin')).toBeNull();
  });

  it('shows a loading state and a retry when the sample data cannot be loaded', async () => {
    api.getStepTestInfo.mockRejectedValueOnce(new Error('Server went away'));
    render(<StepTestPanel node={node()} active onOpenSetup={onSetup} />);
    expect(screen.getByTestId('flow-step-test-loading')).toBeTruthy();
    expect((await screen.findByTestId('flow-step-test-load-error')).textContent).toContain('Server went away');
    api.getStepTestInfo.mockResolvedValue(info());
    fireEvent.click(screen.getByTestId('flow-step-test-retry'));
    await screen.findByTestId('flow-step-test');
  });

  it('says plainly when a step reads nothing from earlier steps and when there is no sample', async () => {
    await open(node(), { parts: [] });
    expect(screen.getByTestId('flow-step-test-no-input')).toBeTruthy();
    cleanup();
    await open(node(), { parts: [{ key: 'input', title: 'What the flow starts with', kind: 'input', source: 'none', value: null, shortened: false, ran_at: null }] });
    expect(screen.getByTestId('flow-step-test-part-empty-input').textContent).toContain('Nothing yet');
  });

  it('shows view-only people nothing from the server', async () => {
    ctx.canManage = false;
    render(<StepTestPanel node={node({ sample: { secret: 'x' } })} active onOpenSetup={onSetup} />);
    expect(screen.getByTestId('flow-step-test-viewonly').textContent).toContain('Ask a flow editor');
    expect(api.getStepTestInfo).not.toHaveBeenCalled();
    expect(screen.queryByText('x')).toBeNull();
  });

  it('does not offer testing on a phone', () => {
    view.isPhone = true;
    render(<StepTestPanel node={node()} active onOpenSetup={onSetup} />);
    expect(screen.getByTestId('flow-step-test-phone').textContent).toContain('larger screen');
    expect(api.getStepTestInfo).not.toHaveBeenCalled();
  });

  it('reads the sample data again each time the tab is opened', async () => {
    api.getStepTestInfo.mockResolvedValue(info());
    const view = render(<StepTestPanel node={node()} active={false} onOpenSetup={onSetup} />);
    expect(api.getStepTestInfo).not.toHaveBeenCalled();
    view.rerender(<StepTestPanel node={node()} active onOpenSetup={onSetup} />);
    await screen.findByTestId('flow-step-test');
    expect(api.getStepTestInfo).toHaveBeenCalledTimes(1);
  });
});

describe('Test tab: a trigger', () => {
  const trigger = (data: Partial<FlowNode['data']> = {}) => node({ nodeType: 'trigger', label: 'New order', ...data }, 't1');
  const tinfo = (kind: StepTestInfo['trigger_kind'], over: Partial<StepTestInfo> = {}) => ({ trigger: true, trigger_kind: kind, parts: [], node_id: 't1', ...over });

  it('uses the last received request and pins it', async () => {
    await open(trigger(), tinfo('webhook'));
    trig.getLastWebhookRequest.mockResolvedValue({ found: true, sample: { email: 'a@b.co' }, received_at: '2026-10-30 10:00:00' });
    fireEvent.click(screen.getByTestId('flow-step-test-last'));
    await screen.findByTestId('flow-step-test-result');
    expect(screen.getByText('a@b.co')).toBeTruthy();
    fireEvent.click(screen.getByTestId('flow-step-pin'));
    expect(ctx.value.updateNodeData.mock.calls[0][1]({ label: 'x', nodeType: 'trigger', configured: true }).sample).toEqual({ email: 'a@b.co' });
  });

  it('says so when nothing has called the web address', async () => {
    await open(trigger(), tinfo('webhook'));
    trig.getLastWebhookRequest.mockResolvedValue({ found: false, sample: null, received_at: null });
    fireEvent.click(screen.getByTestId('flow-step-test-last'));
    expect((await screen.findByTestId('flow-step-test-trigger-note')).textContent).toContain('Nothing has called');
  });

  it('waits for a test request and shows it when it arrives', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      await open(trigger(), tinfo('webhook'));
      trig.getLastWebhookRequest.mockResolvedValueOnce({ found: false, sample: null, received_at: null });
      fireEvent.click(screen.getByTestId('flow-step-test-wait'));
      await screen.findByTestId('flow-step-test-waiting');
      trig.getLastWebhookRequest.mockResolvedValue({ found: true, sample: { hello: 'world' }, received_at: '2026-10-30 10:01:00' });
      await vi.advanceTimersByTimeAsync(2100);
      await screen.findByTestId('flow-step-test-result');
      expect(screen.getByText('world')).toBeTruthy();
      expect(screen.queryByTestId('flow-step-test-waiting')).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('lists recent documents and brings one in', async () => {
    await open(trigger(), tinfo('doc-event', { doctype: 'ToDo' }));
    api.listRecentDocuments.mockResolvedValue({ doctype: 'ToDo', documents: [{ name: 'TD-1', title: 'Call Ada', modified: '2026-10-30 09:00:00' }] });
    api.getDocumentSample.mockResolvedValue({ sample: { description: 'Call Ada' }, shortened: false });
    fireEvent.click(screen.getByTestId('flow-step-test-docs'));
    fireEvent.click(await screen.findByTestId('flow-step-test-doc-TD-1'));
    await screen.findByTestId('flow-step-test-result');
    expect(api.getDocumentSample).toHaveBeenCalledWith('flow-1', 't1', 'TD-1');
  });

  it('simulates a schedule tick on the server', async () => {
    await open(trigger(), tinfo('schedule'));
    api.testStep.mockResolvedValue(result({ mode: 'simulated', summary: 'Pretending the schedule just fired', output: { cron: '0 9 * * *' } }));
    fireEvent.click(screen.getByTestId('flow-step-test-tick'));
    expect((await screen.findByTestId('flow-step-test-summary')).textContent).toContain('Pretending');
  });
});
