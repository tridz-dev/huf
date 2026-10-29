import { describe, expect, it } from 'vitest';
import { publishedToast, startSummary } from './flowPublishSummary';

const ORIGIN = 'https' + '://acme.example';

describe('publish summary wording', () => {
  it('names the address a webhook flow listens on', () => {
    const s = startSummary({ type: 'webhook' }, 'flow-1', ORIGIN);
    expect(s.kind).toBe('webhook');
    expect(s.text).toBe('when a request hits this address');
    expect(s.url?.startsWith(ORIGIN)).toBe(true);
    expect(s.url).toContain('flow_webhook_clean?flow_id=flow-1');
  });
  it('says when a schedule runs', () => {
    expect(startSummary({ type: 'schedule', cron: '0 9 * * *' }, 'f', 'o').text).toBe('every day at 09:00');
    expect(startSummary({ type: 'schedule', cron: '*/15 * * * *' }, 'f', 'o').text).toBe('every 15 minutes');
    expect(startSummary({ type: 'schedule', cron: '' }, 'f', 'o').kind).toBe('none');
  });
  it('says which record change starts a data flow', () => {
    expect(startSummary({ type: 'doc-event', doctype: 'ToDo', event: 'after_insert' }, 'f', 'o').text).toBe('when a ToDo is created');
    expect(startSummary({ type: 'doc-event' }, 'f', 'o').kind).toBe('none');
  });
  it('has a calm success toast', () => {
    expect(publishedToast(startSummary({ type: 'schedule', cron: '0 9 * * *' }, 'f', 'o'))).toEqual({
      title: 'Flow is live',
      description: 'It will now start by itself every day at 09:00. Unpublish to turn it off.',
    });
    expect(publishedToast(startSummary(undefined, 'f', 'o')).description).toBe('It is live, but nothing starts it yet.');
  });
});
