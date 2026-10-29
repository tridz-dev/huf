import { describe, it, expect } from 'vitest';
import { describeZone, runTimesSentence, scheduleZoneSentence, zoneOffsetLabel } from './flowTimeZone';

describe('flowTimeZone', () => {
  const at = new Date('2026-10-28T12:00:00Z');
  it('names the offset of a zone', () => {
    expect(zoneOffsetLabel('Asia/Kolkata', at)).toBe('UTC+05:30');
    expect(zoneOffsetLabel('UTC', at)).toBe('UTC');
    expect(describeZone('Asia/Kolkata', at)).toBe('Asia/Kolkata (UTC+05:30)');
    expect(describeZone(null)).toBe('');
  });
  it('explains schedule and run time zones', () => {
    expect(scheduleZoneSentence(null)).toMatch(/time zone of this site/);
    expect(scheduleZoneSentence('Asia/Kolkata')).toMatch(/site's time zone: Asia\/Kolkata/);
    expect(runTimesSentence('Asia/Kolkata')).toMatch(/browser's time zone/);
  });
});
