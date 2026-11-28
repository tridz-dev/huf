// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { humanizeFlowError, summarizeIssues, validateFlow, validateNode, type NodeLike } from './flowValidation';

const action = (id: string, actionConfig: Record<string, unknown>): NodeLike => ({
  id,
  data: { label: id, nodeType: 'action', actionConfig },
});
const trigger = (triggerConfig: Record<string, unknown>): NodeLike => ({
  id: 't',
  data: { label: 'Webhook', nodeType: 'trigger', triggerConfig },
});

describe('flowValidation', () => {
  it('requires a webhook secret of 32+ chars and GET/POST', () => {
    expect(validateNode(trigger({ type: 'webhook', method: 'PUT', secret: 'abc' }), []).map((i) => i.field)).toEqual(['method', 'secret']);
    expect(validateNode(trigger({ type: 'webhook', method: 'POST', secret: 'abcdefgh1234abcdefgh1234abcdefgh' }), [])).toEqual([]);
  });

  it('does not ask a viewer for a webhook secret the server hid from them', () => {
    expect(validateNode(trigger({ type: 'webhook', method: 'POST', secret: null, secret_hidden: true }), [])).toEqual([]);
    expect(validateNode(trigger({ type: 'webhook', method: 'POST', secret: null }), []).map((i) => i.field)).toEqual(['secret']);
  });

  it('validates schedule cron and doc-event fields', () => {
    expect(validateNode(trigger({ type: 'schedule', cron: '* *' }), [])[0].field).toBe('cron');
    expect(validateNode(trigger({ type: 'doc-event' }), []).map((i) => i.field)).toEqual(['doctype', 'event']);
  });

  it('checks preset tool inputs', () => {
    const n = action('e', { type: 'tool-call', tool_id: 'gmail_send_email', input: { to: 'a@b.c' } });
    expect(validateNode(n, []).map((i) => i.field)).toEqual(['input.subject', 'input.body']);
  });

  it('requires condition branches from edges', () => {
    const n = action('c', { type: 'condition', expression: "input['a'] > 1" });
    expect(validateNode(n, [{ source: 'c', target: 'x', sourceHandle: 'true' }] as never).map((i) => i.field)).toEqual(['branch.false']);
  });

  it('requires an approver type on human approval', () => {
    const n = action('h', { type: 'human.approval', message: 'ok?' });
    const edges = [
      { source: 'h', target: 'a', sourceHandle: 'approve' },
      { source: 'h', target: 'b', sourceHandle: 'reject' },
    ] as never;
    expect(validateNode(n, edges).map((i) => i.field)).toContain('approver_type');
    const ok = action('h', { type: 'human.approval', message: 'ok?', approver_type: 'role', approver_role: 'Sales Manager' });
    expect(validateNode(ok, edges).map((i) => i.field)).not.toContain('approver_type');
  });

  it('checks Execute code: code, profile, size, time limit and input names', () => {
    const ok = { type: 'code-run', code: 'result = 1', profile: 'Flow Scratch', inputs: {}, timeout_s: 30 };
    expect(validateNode(action('x', ok), [])).toEqual([]);
    const blank = validateNode(action('x', { ...ok, code: '  ', profile: '' }), []);
    expect(blank.map((i) => [i.field, i.message])).toEqual([
      ['code', 'Add the Python code to run.'],
      ['profile', 'Choose how the code is allowed to run.'],
    ]);
    expect(validateNode(action('x', { ...ok, code: 'a'.repeat(65537) }), []).map((i) => i.field)).toEqual(['code']);
    expect(validateNode(action('x', { ...ok, timeout_s: 0 }), []).map((i) => i.field)).toEqual(['timeout_s']);
    expect(validateNode(action('x', { ...ok, inputs: { '': 1 } }), []).map((i) => i.field)).toEqual(['inputs']);
    expect(validateNode(action('x', ok), [])[0]?.kind).toBeUndefined();
  });

  it('requires a trigger in a flow and summarises', () => {
    const issues = validateFlow([action('a', { type: 'agent-run' })], []);
    expect(issues[0].field).toBe('trigger');
    expect(summarizeIssues(issues)).toContain('more to fix');
  });

  it('humanises raw schema errors', () => {
    expect(humanizeFlowError(new Error("'agent' is not valid under any of the given schemas"))).toMatch(/not valid/);
    expect(humanizeFlowError(new Error("'prompt' is a required property"))).toMatch(/prompt/);
    expect(humanizeFlowError(new Error('<b>x</b>boom'))).toBe('xboom');
  });

  it('wait: asks for the time, caps it, and checks the date and the give-up path', () => {
    const fields = (cfg: Record<string, unknown>, edges: unknown[] = []) => validateNode(action('w', { type: 'wait', ...cfg }), edges as never).map((i) => [i.field, i.message]);
    expect(fields({ mode: 'duration', duration: { unit: 'hours' } })).toEqual([['duration.value', 'Enter how long to wait.']]);
    expect(fields({ mode: 'duration', duration: { value: 2, unit: 'days' } })).toEqual([]);
    expect(fields({ mode: 'duration', duration: { value: 400, unit: 'days' } })).toEqual([['duration.value', 'A wait can be at most 365 days.']]);
    expect(fields({ mode: 'duration', duration: { value: 9000, unit: 'hours' } })).toEqual([['duration.value', 'A wait can be at most 365 days.']]);
    expect(fields({ mode: 'until' })).toEqual([['until', 'Choose when to continue.']]);
    expect(fields({ mode: 'until', until: '2030-01-31 09:00' })).toEqual([]);
    expect(fields({ mode: 'resume' })).toEqual([]);
    expect(fields({ mode: 'resume' }, [{ source: 'w', target: 'x', sourceHandle: 'timeout', data: { route: 'timeout' } }])).toEqual([['resume.timeout_ms', 'Choose how long to wait before giving up.']]);
  });

  const check = (cfg: Record<string, unknown>) => validateNode(action('n', cfg), []).map((i) => [i.field, i.message]);

  it('retry: tries 2 to 10 and a first wait of at least a minute', () => {
    const tool = (retry: unknown) => check({ type: 'tool-call', tool_id: 'http_request', input: { url: 'https://x.test' }, retry });
    expect(tool(undefined)).toEqual([]);
    expect(tool({ attempts: 3, backoff: 'fixed', delay_seconds: 60 })).toEqual([]);
    expect(tool({ attempts: 1, backoff: 'fixed', delay_seconds: 60 })).toEqual([['retry.attempts', 'Tries must be between 2 and 10.']]);
    expect(tool({ attempts: 11, backoff: 'fixed', delay_seconds: 60 })).toEqual([['retry.attempts', 'Tries must be between 2 and 10.']]);
    expect(tool({ attempts: 3, backoff: 'fixed', delay_seconds: 30 })).toEqual([['retry.delay_seconds', 'The first wait must be at least 1 minute.']]);
  });

  it('stop, find, update and run-another-flow ask for their required fields', () => {
    expect(check({ type: 'stop', message: '' })).toEqual([['message', 'Write the message to show when the flow stops.']]);
    expect(check({ type: 'stop', message: 'No stock' })).toEqual([]);
    expect(check({ type: 'doc-get' })).toEqual([['doctype', 'Choose a document type.']]);
    expect(check({ type: 'doc-get', doctype: 'ToDo' })).toEqual([['name', 'Choose which document to find.']]);
    expect(check({ type: 'doc-get', doctype: 'ToDo', filters: {} })).toEqual([['filters', 'Add at least one field to match.']]);
    expect(check({ type: 'doc-get', doctype: 'ToDo', filters: { status: 'Open' } })).toEqual([]);
    expect(check({ type: 'doc-update', doctype: 'ToDo', name: '', values: {} })).toEqual([
      ['name', 'Choose which document to update.'],
      ['values', 'Add at least one field to change.'],
    ]);
    expect(check({ type: 'doc-update', doctype: 'ToDo', name: 'T-1', values: { status: 'Closed' } })).toEqual([]);
    expect(check({ type: 'flow-call', flow_id: '' })).toEqual([['flow_id', 'Choose a flow to run.']]);
    expect(check({ type: 'flow-call', flow_id: 'onboarding' })).toEqual([]);
  });
});
