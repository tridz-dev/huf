import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/frappe-sdk', () => ({ call: { get: vi.fn(), post: vi.fn() } }));
import {
  canExplainEvent,
  eventStatusLabel,
  eventStatusTone,
  failedCount,
  formatCost,
  formatTokens,
  type HealthCounts,
} from './gatewayHealthApi';

describe('gatewayHealthApi helpers', () => {
  it('maps statuses to plain labels', () => {
    expect(eventStatusLabel('Rejected')).toBe('Blocked');
    expect(eventStatusLabel('Unrouted')).toBe('No destination');
    expect(eventStatusLabel('Other')).toBe('Other');
  });

  it('maps statuses to tones', () => {
    expect(eventStatusTone('Succeeded')).toBe('success');
    expect(eventStatusTone('Failed')).toBe('danger');
    expect(eventStatusTone('Rejected')).toBe('warning');
    expect(eventStatusTone('Queued')).toBe('neutral');
  });

  it('knows which events can be explained', () => {
    expect(canExplainEvent('Rejected')).toBe(true);
    expect(canExplainEvent('Succeeded')).toBe(false);
  });

  it('formats cost and tokens', () => {
    expect(formatCost(0)).toBe('$0.00');
    expect(formatCost(0.004)).toBe('<$0.01');
    expect(formatCost(1.234)).toBe('$1.23');
    expect(formatTokens(950)).toBe('950');
    expect(formatTokens(12500)).toBe('12.5k');
    expect(formatTokens(2_000_000)).toBe('2.0M');
  });

  it('counts problems', () => {
    const counts = { Failed: 2, Rejected: 1, Unrouted: 3 } as HealthCounts;
    expect(failedCount(counts)).toBe(6);
  });
});
