import { describe, expect, it } from 'vitest';
import { parseCron } from '../flow-trigger/cronFields';
import { HOUR_STEPS, MINUTE_STEPS, DEFAULT_PICKER, cronProblem, cronToPicker, pickerForKind, pickerToCron } from './flowSchedule';
import { clock, describeCron, fixedClockTime, hourWord, hoursHelper } from '../flow-trigger/scheduleText';
import { clockInOtherZone, formatWall, instantOf, nextRuns, wallIn } from '../flow-trigger/scheduleRuns';

describe('pickerToCron', () => {
  it('compiles every picker kind to a 5-part cron', () => {
    expect(pickerToCron({ ...DEFAULT_PICKER, kind: 'minutes', every: 15 })).toBe('*/15 * * * *');
    expect(pickerToCron({ ...DEFAULT_PICKER, kind: 'hours', every: 2, minute: 30 })).toBe('30 */2 * * *');
    expect(pickerToCron({ ...DEFAULT_PICKER, kind: 'daily', hour: 8, minute: 5 })).toBe('5 8 * * *');
    expect(pickerToCron({ ...DEFAULT_PICKER, kind: 'weekly', weekdays: [3] })).toBe('0 9 * * 3');
    expect(pickerToCron({ ...DEFAULT_PICKER, kind: 'monthly', monthday: 15 })).toBe('0 9 15 * *');
  });

  it('weekly keeps several days and writes Monday to Friday as a range', () => {
    expect(pickerToCron({ ...DEFAULT_PICKER, kind: 'weekly', weekdays: [5, 1, 3] })).toBe('0 9 * * 1,3,5');
    expect(pickerToCron({ ...DEFAULT_PICKER, kind: 'weekly', weekdays: [1, 2, 3, 4, 5] })).toBe('0 9 * * 1-5');
    expect(pickerToCron({ ...DEFAULT_PICKER, kind: 'weekly', weekdays: [0, 6] })).toBe('0 9 * * 0,6');
    expect(pickerToCron({ ...DEFAULT_PICKER, kind: 'weekly', weekdays: [0, 1, 2, 3, 4, 5, 6] })).toBe('0 9 * * *');
  });

  it('monthly offers days 1-31 and the last day', () => {
    expect(pickerToCron({ ...DEFAULT_PICKER, kind: 'monthly', monthday: 31 })).toBe('0 9 31 * *');
    expect(pickerToCron({ ...DEFAULT_PICKER, kind: 'monthly', monthday: 'last' })).toBe('0 9 L * *');
    expect(pickerToCron({ ...DEFAULT_PICKER, kind: 'monthly', monthday: 40 })).toBe('0 9 31 * *');
  });

  it('B8: every N hours is every N from midnight, never a gap that jumps back (15 hours is spelled out)', () => {
    for (const every of HOUR_STEPS) {
      const cron = pickerToCron({ ...DEFAULT_PICKER, kind: 'hours', every });
      const hours = parseCron(cron)!.hours;
      const gaps = hours.map((h, i) => (hours[(i + 1) % hours.length] - h + 24) % 24 || 24);
      expect(new Set(gaps).size).toBe(1);
    }
    expect(pickerToCron({ ...DEFAULT_PICKER, kind: 'hours', every: 15 })).toBe('0 0,15 * * *');
    expect(pickerToCron({ ...DEFAULT_PICKER, kind: 'hours', every: 5 })).toBe('0 0,5,10,15,20 * * *');
  });

  it('switching kind never carries minutes into hours', () => {
    const minutes = pickerForKind('minutes', DEFAULT_PICKER);
    expect(minutes.every).toBe(15);
    const hours = pickerForKind('hours', minutes);
    expect(hours.every).toBe(1);
    expect(pickerToCron(hours)).toBe('0 */1 * * *');
  });
});

describe('cronToPicker', () => {
  it('round-trips the friendly shapes', () => {
    for (const kind of ['minutes', 'hours', 'daily', 'weekly', 'monthly'] as const) {
      const p = { ...DEFAULT_PICKER, kind, every: kind === 'minutes' ? 15 : 3 };
      const back = cronToPicker(pickerToCron(p));
      expect(back.kind).toBe(kind);
      expect(pickerToCron(back)).toBe(pickerToCron(p));
    }
    expect(cronToPicker('0 9 * * 1-5')).toMatchObject({ kind: 'weekly', weekdays: [1, 2, 3, 4, 5] });
    expect(cronToPicker('30 18 L * *')).toMatchObject({ kind: 'monthly', monthday: 'last', hour: 18, minute: 30 });
    expect(cronToPicker('0 9 31 * *')).toMatchObject({ kind: 'monthly', monthday: 31 });
  });

  it('falls back to custom for anything else, including a stored 15-hour step', () => {
    expect(cronToPicker('0 9 1-5 * 1,2').kind).toBe('custom');
    expect(cronToPicker('*/5 9-17 * * 1-5').kind).toBe('custom');
    expect(cronToPicker('0 */15 * * *').kind).toBe('custom');
    expect(cronToPicker('*/45 * * * *').kind).toBe('custom');
    expect(cronToPicker('garbage').kind).toBe('custom');
    expect(MINUTE_STEPS).toContain(15);
  });
});

describe('cronProblem', () => {
  it('B7: the business-hours cron is valid and says nothing', () => {
    expect(cronProblem('*/5 9-17 * * 1-5')).toBeNull();
  });
  it('accepts names, L and a Sunday written as 7', () => {
    for (const c of ['0 9 * * mon-fri', '0 9 L * *', '0 9 * * 7', '0 0 1 jan *', '5/15 * * * *']) expect(cronProblem(c)).toBeNull();
  });
  it('says what to do about a bad one', () => {
    expect(cronProblem('')).toMatch(/Choose when/);
    expect(cronProblem('* * *')).toMatch(/5 parts/);
    expect(cronProblem('a b c d e')).toMatch(/not valid/);
    expect(cronProblem('61 25 * * *')).toMatch(/out of range/);
    expect(cronProblem('*/0 * * * *')).toMatch(/out of range/);
    expect(cronProblem('5-1 * * * *')).toMatch(/out of range/);
    expect(cronProblem('0 9 * * 8')).toMatch(/out of range/);
  });
});

describe('describeCron', () => {
  it('keeps the short familiar sentences for the friendly shapes', () => {
    expect(describeCron('0 9 * * 1')).toBe('Every Monday at 09:00');
    expect(describeCron('30 14 * * *')).toBe('Every day at 14:30');
    expect(describeCron('*/15 * * * *')).toBe('Every 15 minutes');
    expect(describeCron('* * * * *')).toBe('Every minute');
    expect(describeCron('30 14 15 * *')).toBe('On day 15 of every month at 14:30');
    expect(describeCron('0 9 L * *')).toBe('On the last day of every month at 09:00');
    expect(describeCron('0 9 * * 1,3,5')).toBe('Every Monday, Wednesday and Friday at 09:00');
    expect(describeCron('0 9 * * 1-5')).toBe('Every Monday to Friday at 09:00');
    expect(describeCron('0 9 * * 0,6')).toBe('Every Saturday and Sunday at 09:00');
    expect(describeCron('')).toBe('No valid schedule yet.');
    expect(describeCron('61 25 * * *')).toBe('No valid schedule yet.');
  });

  it('w1cap-04: the helper under the box names the same times as the summary, also for minute 30', () => {
    expect(hoursHelper(3, 0)).toBe('Counted from midnight, so 3 hours means 00:00, 03:00, 06:00 and so on.');
    expect(hoursHelper(3, 30)).toContain('00:30, 03:30, 06:30');
    expect(describeCron('30 */3 * * *')).toContain('00:30, 03:30, 06:30');
  });

  it('B8: hours are described as from midnight, and a stored 15-hour step tells the truth', () => {
    expect(describeCron('0 */3 * * *')).toBe('Every 3 hours from midnight (00:00, 03:00, 06:00 and so on)');
    expect(describeCron('30 */6 * * *')).toBe('Every 6 hours from midnight (00:30, 06:30, 12:30 and so on)');
    expect(describeCron('0 */1 * * *')).toBe('Every hour, on the hour');
    expect(describeCron('0 */15 * * *')).toBe('At 00:00 and 15:00, every day');
  });

  it('B7: spells out a custom cron in words', () => {
    expect(describeCron('*/5 9-17 * * 1-5')).toBe('Every 5 minutes, 9am to 5pm, Monday to Friday');
    expect(describeCron('0 9,13,17 * * *')).toBe('At 09:00, 13:00 and 17:00, every day');
    expect(describeCron('*/10 * * * 1')).toBe('Every 10 minutes, Mondays');
    expect(describeCron('0 9-17 * * *')).toBe('Every hour from 9am to 5pm');
    expect(describeCron('0 9 1 jan,apr *')).toBe('At 09:00, on day 1 of the month, in January and April');
    expect(describeCron('0 8 1,15 * *')).toBe('At 08:00, on days 1 and 15 of the month');
    expect(describeCron('0 9 * 1-3 *')).toBe('At 09:00, every day, from January to March');
  });

  it('never prints the raw expression or a zone', () => {
    for (const c of ['*/5 9-17 * * 1-5', '0 */15 * * *', '0 9 1 jan,apr *']) {
      const text = describeCron(c);
      expect(text).not.toMatch(/\*|server time|cron/i);
    }
  });
});

describe('helpers', () => {
  it('formats clock times and hours', () => {
    expect(clock(9, 5)).toBe('09:05');
    expect([0, 9, 12, 17, 23].map(hourWord)).toEqual(['12am', '9am', '12pm', '5pm', '11pm']);
  });
  it('knows when a schedule has one fixed time', () => {
    expect(fixedClockTime('30 14 * * *')).toEqual({ hour: 14, minute: 30 });
    expect(fixedClockTime('*/5 9-17 * * *')).toBeNull();
    expect(fixedClockTime('0 9,13 * * *')).toBeNull();
  });
});

describe('nextRuns', () => {
  const from = new Date('2026-10-30T03:00:00Z'); // 08:30 in Kolkata, Friday

  it('lists the next runs on the chosen zone clock', () => {
    const runs = nextRuns('0 9 * * *', 'Asia/Kolkata', 3, from);
    expect(runs.map((r) => formatWall(r.wall))).toEqual(['Fri 30 Oct, 09:00', 'Sat 31 Oct, 09:00', 'Sun 1 Nov, 09:00']);
    expect(runs[0].at.toISOString()).toBe('2026-10-30T03:30:00.000Z');
  });

  it('the same 09:00 is a different moment in another zone', () => {
    const london = nextRuns('0 9 * * *', 'Europe/London', 1, from)[0];
    expect(formatWall(london.wall)).toBe('Fri 30 Oct, 09:00');
    expect(london.at.toISOString()).toBe('2026-10-30T09:00:00.000Z');
  });

  it('B7: business hours skip the weekend', () => {
    const friday = new Date('2026-10-30T11:50:00Z'); // 17:20 in Kolkata
    const runs = nextRuns('*/5 9-17 * * 1-5', 'Asia/Kolkata', 3, friday);
    expect(runs.map((r) => formatWall(r.wall))).toEqual(['Fri 30 Oct, 17:25', 'Fri 30 Oct, 17:30', 'Fri 30 Oct, 17:35']);
    const late = nextRuns('*/5 9-17 * * 1-5', 'Asia/Kolkata', 1, new Date('2026-10-30T12:30:00Z'))[0]; // 18:00 Friday
    expect(formatWall(late.wall)).toBe('Mon 2 Nov, 09:00');
  });

  it('last day and day 31 skip short months', () => {
    expect(nextRuns('0 9 L * *', 'UTC', 3, from).map((r) => formatWall(r.wall))).toEqual(['Sat 31 Oct, 09:00', 'Mon 30 Nov, 09:00', 'Thu 31 Dec, 09:00']);
    expect(nextRuns('0 9 31 * *', 'UTC', 3, from).map((r) => formatWall(r.wall))).toEqual(['Sat 31 Oct, 09:00', 'Thu 31 Dec, 09:00', 'Sun 31 Jan, 09:00']);
  });

  it('is empty for an invalid cron and never loops forever on one that never fires', () => {
    expect(nextRuns('nonsense', 'UTC', 3, from)).toEqual([]);
    expect(nextRuns('0 9 31 2 *', 'UTC', 3, from)).toEqual([]);
  });

  it('shows how a daily time reads in the browser zone', () => {
    expect(clockInOtherZone(9, 0, 'Asia/Kolkata', 'UTC', from)).toBe('03:30');
    expect(clockInOtherZone(9, 0, 'UTC', 'Asia/Kolkata', from)).toBe('14:30');
  });

  it('round-trips wall clock to a moment and back', () => {
    const wall = { y: 2026, m: 10, d: 30, h: 9, mi: 0 };
    expect(wallIn('Asia/Kolkata', instantOf('Asia/Kolkata', wall))).toEqual(wall);
    expect(wallIn('America/New_York', instantOf('America/New_York', wall))).toEqual(wall);
  });
});
