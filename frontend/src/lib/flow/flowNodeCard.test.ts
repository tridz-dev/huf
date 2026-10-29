// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { actionOptions } from '../../data/actions';
import { actionSubtitle, cardStatus, triggerSubtitle } from './flowNodeCard';

describe('cardStatus', () => {
  const base = { runStatus: undefined, incomplete: false, orphaned: false, notConnected: false } as const;

  it('says Ready when nothing is wrong', () => {
    expect(cardStatus(base)).toEqual({ kind: 'ready', text: 'Ready' });
  });

  it('shows exactly one word, most important first', () => {
    expect(cardStatus({ ...base, incomplete: true, notConnected: true }).text).toBe('Not connected');
    expect(cardStatus({ ...base, incomplete: true, orphaned: true }).text).toBe('Needs setup');
    expect(cardStatus({ ...base, orphaned: true }).text).toBe('Nothing leads here');
    expect(cardStatus({ ...base, incomplete: true, runStatus: 'error' }).text).toBe('Failed');
    expect(cardStatus({ ...base, runStatus: 'success' }).text).toBe('Done');
    expect(cardStatus({ ...base, runStatus: 'running', incomplete: true }).text).toBe('Running');
  });
});

describe('actionSubtitle', () => {
  it('names the channel, recipient and host when they are plain text', () => {
    expect(actionSubtitle({ type: 'tool-call', tool_id: 'slack_send_message', input: { channel: '#alerts' } })).toBe('Send a message to #alerts');
    expect(actionSubtitle({ type: 'tool-call', tool_id: 'gmail_send_email', input: { to: 'ada@example.com' } })).toBe('Send an email to ada@example.com');
    expect(actionSubtitle({ type: 'tool-call', tool_id: 'http_request', input: { url: 'https://example.com/api' } })).toBe('Call example.com');
  });

  it('falls back to a plain sentence when the value is a reference or empty', () => {
    expect(actionSubtitle({ type: 'tool-call', tool_id: 'slack_send_message', input: { channel: { $from: 't.channel' } } })).toBe('Send a Slack message');
    expect(actionSubtitle({ type: 'agent-run', agent: '' })).toBe('Ask an AI agent to do a task');
    expect(actionSubtitle({ type: 'tool-call', tool_id: '' })).toBe('Pick what it should do');
  });

  it('describes every palette step without internal words', () => {
    const configs: Record<string, Parameters<typeof actionSubtitle>[0]> = {
      'agent-run': { type: 'agent-run' },
      router: { type: 'router' },
      condition: { type: 'condition' },
      loop: { type: 'foreach' },
      'human.approval': { type: 'human.approval' },
      transform: { type: 'transform', op: 'lower' },
      'state-get': { type: 'state-get' },
      'state-set': { type: 'state-set' },
      'state-delete': { type: 'state-delete' },
      'doc-create': { type: 'doc-create' },
      'code-run': { type: 'code-run' },
    };
    for (const [id, cfg] of Object.entries(configs)) {
      const text = actionSubtitle(cfg);
      expect(text, id).not.toBe('');
      expect(text, id).not.toMatch(/\b(tool|json|doctype|state|router|foreach)\b/i);
    }
  });
});

describe('triggerSubtitle', () => {
  it('reads like a sentence', () => {
    expect(triggerSubtitle({ type: 'schedule', cron: '0 9 * * 1-5' })).toBe('Runs on a custom schedule');
    expect(triggerSubtitle({ type: 'schedule', cron: '0 9 * * *' })).toBe('Every day at 09:00');
    expect(triggerSubtitle({ type: 'doc-event', doctype: 'ToDo', event: 'after_insert' })).toBe('When a ToDo is created');
    expect(triggerSubtitle({ type: undefined })).toBe('Choose what starts this flow');
  });
});

describe('palette vocabulary', () => {
  it('uses plain names and keeps ids stable', () => {
    const byId = Object.fromEntries(actionOptions.map((a) => [a.id, a.name]));
    expect(byId['human.approval']).toBe('Wait for approval');
    expect(byId.router).toBe('Choose with AI');
    expect(byId['state-set']).toBe('Save data for later');
    expect(byId['agent-run']).toBe('Run agent');
    expect(actionOptions.find((a) => a.id === 'agent-run')?.icon).toBe('SquareAsterisk');
    for (const a of actionOptions) {
      expect(a.name, a.id).not.toMatch(/Control Flow|LLM|Human in Loop|Call tool|If\/Else/);
      expect((a.description ?? '').length, a.id).toBeLessThanOrEqual(52);
    }
    expect(new Set(actionOptions.map((a) => a.name)).size).toBe(actionOptions.length);
  });
});
