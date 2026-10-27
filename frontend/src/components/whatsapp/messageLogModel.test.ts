import { describe, expect, it } from 'vitest';
import {
  displayStatus,
  activeFilterCount, agentRunPath, EMPTY_FILTERS, filtersFromParams, filtersToParams, filtersToQuery, messagePreview,
  sentByLabel, statusTicks, statusTimeline,
} from './messageLogModel';

describe('filters and URL', () => {
  it('round-trips filters and keeps unrelated params', () => {
    const filters = { ...EMPTY_FILTERS, q: 'order', direction: 'out' as const, status: 'failed', from: '2026-01-01' };
    const params = filtersToParams(filters, new URLSearchParams('gateway=GW&tab=messages'));
    expect(params.get('gateway')).toBe('GW');
    expect(params.get('tab')).toBe('messages');
    expect(filtersFromParams(params)).toEqual(filters);
  });
  it('drops empty values and ignores a bad direction', () => {
    const params = filtersToParams(EMPTY_FILTERS, new URLSearchParams('q=old&gateway=GW'));
    expect(params.toString()).toBe('gateway=GW');
    expect(filtersFromParams(new URLSearchParams('direction=sideways')).direction).toBe('');
  });
  it('counts active filters and builds the server query', () => {
    const filters = { ...EMPTY_FILTERS, phone: ' 1555 ', to: '2026-02-01', agent: 'A1' };
    expect(activeFilterCount(filters)).toBe(3);
    expect(activeFilterCount(EMPTY_FILTERS)).toBe(0);
    expect(filtersToQuery(filters)).toEqual({ phone: '1555', date_to: '2026-02-01', agent: 'A1' });
  });
});

describe('status and labels', () => {
  it('maps statuses to ticks and tone', () => {
    expect(statusTicks('sent')).toMatchObject({ ticks: 1, tone: 'neutral' });
    expect(statusTicks('Delivered')).toMatchObject({ ticks: 2, tone: 'neutral' });
    expect(statusTicks('read')).toMatchObject({ ticks: 2, tone: 'good' });
    expect(statusTicks('failed')).toMatchObject({ ticks: 0, tone: 'danger' });
    expect(statusTicks(null).label).toBe('Unknown');
    expect(statusTicks('queued').label).toBe('Queued');
  });
  it('labels who sent a message', () => {
    expect(sentByLabel('agent', 'Support bot')).toBe('Support bot');
    expect(sentByLabel('template')).toBe('Template send');
    expect(sentByLabel('manual')).toBe('Manual');
    expect(sentByLabel('customer')).toBe('Customer');
    expect(sentByLabel(null)).toBe('Unknown');
  });
  it('builds the run link only when a run exists', () => {
    expect(agentRunPath({ agent_run: 'RUN-1' })).toBe('/executions/RUN-1');
    expect(agentRunPath({ agent_run: null })).toBeNull();
  });
  it('previews text, template and media messages', () => {
    expect(messagePreview({ text: 'a\n  b', content_type: 'text', template: null })).toBe('a b');
    expect(messagePreview({ text: 'x'.repeat(200), content_type: 'text', template: null }, 10)).toHaveLength(10);
    expect(messagePreview({ text: '', content_type: 'image', template: null })).toBe('[image]');
    expect(messagePreview({ text: null, content_type: 'template', template: 'hello' })).toBe('Template: hello');
  });
  it('builds the status timeline', () => {
    expect(statusTimeline('delivered').map((s) => s.reached)).toEqual([true, true, false]);
    expect(statusTimeline('failed').map((s) => s.key)).toEqual(['sent', 'failed']);
    expect(statusTimeline(null).every((s) => !s.reached)).toBe(true);
  });
});

describe('delivery state and error info', () => {
  it('treats played as reached', async () => {
    const m = await import('./messageLogModel');
    expect(m.statusTicks('played').label).toBe('Played');
    expect(m.statusTimeline('played').every((s) => s.reached)).toBe(true);
  });

  it('classifies Meta error codes and falls back to text hints', async () => {
    const m = await import('./messageLogModel');
    expect(m.errorInfo('(#131047) Re-engagement message')).toMatchObject({ code: 131047, label: 'Window closed' });
    expect(m.errorInfo('request timed out')?.label).toBe('Temporary problem');
    expect(m.errorInfo('')).toBeNull();
  });

describe('displayStatus', () => {
  it('shows incoming messages as received unless they failed', () => {
    expect(displayStatus({ direction: 'in', status: 'Succeeded' })).toBe('received');
    expect(displayStatus({ direction: 'in', status: 'failed' })).toBe('failed');
    expect(displayStatus({ direction: 'out', status: 'delivered' })).toBe('delivered');
  });
});
});
