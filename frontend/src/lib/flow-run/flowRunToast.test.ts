// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { parkedToastText, runToastDetail } from './flowRunToast';

describe('runToastDetail', () => {
  it('uses the flow name and Run #n, never an id', () => {
    expect(runToastDetail('Order intake', 12)).toBe('Order intake · Run #12');
    expect(runToastDetail('Order intake', null)).toBe('Order intake');
    expect(runToastDetail(undefined, 3)).toBe('Run #3');
    expect(runToastDetail(undefined, undefined)).toBe('This run');
  });
});

describe('parkedToastText', () => {
  const now = Date.parse('2026-11-25T06:00:00Z');
  it('says when a timed wait continues', () => {
    expect(parkedToastText('Flow · Run #2', '2026-11-27T11:30:00', now)).toBe('Flow · Run #2. It continues in 2 days.');
    expect(parkedToastText('Flow', '2026-11-25T06:30:00', now)).toBe('Flow. It continues in 30 minutes.');
  });
  it('falls back when the time is unknown', () => {
    expect(parkedToastText('Flow', null, now)).toBe('Flow. It continues on its own.');
  });
});
