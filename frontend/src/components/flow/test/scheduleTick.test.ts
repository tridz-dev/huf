import { describe, expect, it } from 'vitest';
import { scheduleTickRows } from './TestResultView';

describe('scheduleTickRows', () => {
  it('shows the schedule as a sentence and hides the step id and cron text', () => {
    const rows = scheduleTickRows({ scheduled_for: '2026-10-31T09:00:00Z', trigger_node: 'start', cron: '0 9 * * *' })!;
    expect(rows.Schedule).toBe('Runs every day at 09:00');
    expect(Object.values(rows).join(' ')).not.toMatch(/start|\* \*/);
    expect(rows['When it fires']).toBeTruthy();
  });
  it('leaves other outputs alone', () => {
    expect(scheduleTickRows({ cron: '0 9 * * *' })).toBeNull();
  });
});
