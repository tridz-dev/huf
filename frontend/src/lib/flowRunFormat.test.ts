import { describe, expect, it } from 'vitest';
import { describeDecision } from './flowRunFormat';
import { parseServerDate, setSiteTimezoneForTests, toServerDatetime } from './serverTime';

describe('describeDecision', () => {
  it('words an approval with who and when', () => {
    const text = describeDecision({ decision: 'approved', decided_by: 'ana@example.com', decided_at: '2026-10-28T01:45:00Z' });
    expect(text).toMatch(/^Approved by ana@example\.com on /);
  });
  it('words a rejection without a time when none was recorded', () => {
    expect(describeDecision({ decision: 'rejected', decided_by: 'bo@example.com' })).toBe('Rejected by bo@example.com');
  });
  it('words a timeout', () => {
    expect(describeDecision({ decision: 'timeout', comment: null })).toBe('Timed out with no answer');
  });
  it('ignores other step outputs', () => {
    expect(describeDecision({ success: true })).toBeNull();
    expect(describeDecision('x')).toBeNull();
  });
});

describe('server time', () => {
  it('reads naive Frappe datetimes in the site zone', () => {
    setSiteTimezoneForTests('Asia/Kolkata');
    expect(parseServerDate('2026-10-28 07:15:00.123456')?.toISOString()).toBe('2026-10-28T01:45:00.123Z');
    setSiteTimezoneForTests(null);
  });
  it('keeps offset-carrying strings as they are', () => {
    setSiteTimezoneForTests('Asia/Kolkata');
    expect(parseServerDate('2026-10-28T01:45:00Z')?.toISOString()).toBe('2026-10-28T01:45:00.000Z');
    setSiteTimezoneForTests(null);
  });
  it('formats a Date as naive site time for filters', () => {
    setSiteTimezoneForTests('Asia/Kolkata');
    expect(toServerDatetime(new Date('2026-10-28T01:45:00Z'))).toBe('2026-10-28 07:15:00');
    setSiteTimezoneForTests(null);
  });
  it('handles a DST zone', () => {
    setSiteTimezoneForTests('America/New_York');
    expect(parseServerDate('2026-07-01 12:00:00')?.toISOString()).toBe('2026-07-01T16:00:00.000Z');
    expect(parseServerDate('2026-12-01 12:00:00')?.toISOString()).toBe('2026-12-01T17:00:00.000Z');
    setSiteTimezoneForTests(null);
  });
});
