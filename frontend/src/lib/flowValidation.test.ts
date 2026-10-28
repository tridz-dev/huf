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
  it('requires a webhook secret of 8+ chars and GET/POST', () => {
    expect(validateNode(trigger({ type: 'webhook', method: 'PUT', secret: 'abc' }), []).map((i) => i.field)).toEqual(['method', 'secret']);
    expect(validateNode(trigger({ type: 'webhook', method: 'POST', secret: 'abcdefgh' }), [])).toEqual([]);
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
});
