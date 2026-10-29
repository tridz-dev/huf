import { describe, expect, it } from 'vitest';
import { cronProblem, cronToPicker, DEFAULT_PICKER, describeCron, pickerToCron } from './flowSchedule';

describe('flowSchedule', () => {
  it('compiles every picker kind to a 5-part cron', () => {
    expect(pickerToCron({ ...DEFAULT_PICKER, kind: 'minutes', every: 15 })).toBe('*/15 * * * *');
    expect(pickerToCron({ ...DEFAULT_PICKER, kind: 'hours', every: 2, minute: 30 })).toBe('30 */2 * * *');
    expect(pickerToCron({ ...DEFAULT_PICKER, kind: 'daily', hour: 8, minute: 5 })).toBe('5 8 * * *');
    expect(pickerToCron({ ...DEFAULT_PICKER, kind: 'weekly', weekday: 3 })).toBe('0 9 * * 3');
    expect(pickerToCron({ ...DEFAULT_PICKER, kind: 'monthly', monthday: 15 })).toBe('0 9 15 * *');
  });

  it('round-trips friendly crons and falls back to custom', () => {
    for (const kind of ['minutes', 'hours', 'daily', 'weekly', 'monthly'] as const) {
      const cron = pickerToCron({ ...DEFAULT_PICKER, kind });
      expect(cronToPicker(cron).kind).toBe(kind);
    }
    expect(cronToPicker('0 9 1-5 * 1,2').kind).toBe('custom');
  });

  it('validates and describes', () => {
    expect(cronProblem('')).toMatch(/Choose when/);
    expect(cronProblem('* * *')).toMatch(/5 parts/);
    expect(cronProblem('a b c d e')).toMatch(/not valid/);
    expect(cronProblem('61 25 * * *')).toMatch(/out of range/);
    expect(cronProblem('*/0 * * * *')).toMatch(/out of range/);
    expect(cronProblem('*/15 9-17 * * 1-5')).toBeNull();
    expect(cronProblem('*/15 * * * *')).toBeNull();
    expect(describeCron('0 9 * * 1')).toBe('Every Monday at 09:00 (server time)');
    expect(describeCron('')).toBe('No valid schedule yet.');
  });
});
