import { describe, it, expect } from 'vitest';
import { allTimeZones, browserTimeNote, describeZone, runTimesSentence, scheduleZoneLine, zoneOffsetLabel } from './flowTimeZone';

describe('flowTimeZone', () => {
  const at = new Date('2026-10-28T12:00:00Z');
  it('names the offset of a zone', () => {
    expect(zoneOffsetLabel('Asia/Kolkata', at)).toBe('UTC+05:30');
    expect(zoneOffsetLabel('UTC', at)).toBe('UTC');
    expect(describeZone('Asia/Kolkata', at)).toBe('Asia/Kolkata (UTC+05:30)');
    expect(describeZone(null)).toBe('');
  });
  it('explains schedule and run time zones', () => {
    expect(scheduleZoneLine(null, true)).toMatch(/time zone of this site/);
    expect(scheduleZoneLine('Asia/Kolkata', true)).toMatch(/^Runs in Asia\/Kolkata time \(UTC\+05:30\), this site's time zone\.$/);
    expect(scheduleZoneLine('America/New_York', false)).toMatch(/^Runs in America\/New_York time \(UTC-0[45]:00\)\.$/);
    expect(browserTimeNote('03:30', 'Asia/Kolkata')).toMatch(/^Shows as 03:30 in your browser \(.+\)\.$|^$/);
    expect(browserTimeNote('03:30', null)).toBe('');
    expect(runTimesSentence('Asia/Kolkata')).toMatch(/browser's time zone/);
  });
  it('lists time zones', () => {
    const zones = allTimeZones('Asia/Kolkata');
    expect(zones).toContain('UTC');
    expect(zones).toContain('Asia/Kolkata');
  });
});
