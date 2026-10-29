// @vitest-environment jsdom
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { setSiteTimezoneForTests } from '@/lib/serverTime';
import { ScheduleEditor } from './ScheduleEditor';

// The Radix pointer APIs jsdom lacks (the zone list and selects use them only when opened).
beforeEach(() => setSiteTimezoneForTests('Asia/Kolkata'));
afterEach(() => {
  cleanup();
  setSiteTimezoneForTests(null);
});

function Harness({ initial }: { initial?: string }) {
  const [cron, setCron] = useState<string | undefined>(initial);
  const [zone, setZone] = useState<string | undefined>(undefined);
  return <ScheduleEditor cron={cron} timeZone={zone} onChange={setCron} onZoneChange={setZone} />;
}

describe('ScheduleEditor', () => {
  it('a friendly schedule has no cron box, no red text and a sentence with the zone', () => {
    render(<Harness initial="0 9 * * *" />);
    expect(screen.queryByTestId('flow-field-trigger.schedule-cron')).toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.getByTestId('flow-schedule-summary').textContent).toBe('Every day at 09:00 in Asia/Kolkata');
    expect(screen.getAllByTestId('flow-schedule-next-run')).toHaveLength(3);
  });

  it('B7: a valid business-hours pattern shows no error and a plain sentence; fixing a wrong one clears the message at once', () => {
    render(<Harness initial="*/5 9-17 * * 1-5" />);
    const box = screen.getByTestId('flow-field-trigger.schedule-cron') as HTMLInputElement;
    expect(screen.queryByTestId('flow-error-trigger.schedule-cron')).toBeNull();
    expect(screen.getByTestId('flow-schedule-summary').textContent).toContain('Every 5 minutes, 9am to 5pm, Monday to Friday');

    fireEvent.change(box, { target: { value: '61 25 * * *' } });
    expect(screen.getByTestId('flow-error-trigger.schedule-cron').textContent).toMatch(/out of range/);
    expect(screen.getByTestId('flow-schedule-summary').textContent).toBe('No valid schedule yet.');

    fireEvent.change(box, { target: { value: '*/5 9-17 * * 1-5' } });
    expect(screen.queryByTestId('flow-error-trigger.schedule-cron')).toBeNull();
  });

  it('an empty untouched custom pattern says nothing red', () => {
    render(<Harness initial="" />);
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('weekly keeps at least one day and offers the weekday preset', () => {
    render(<Harness initial="0 9 * * 1" />);
    fireEvent.click(screen.getByTestId('flow-field-trigger.schedule-weekday-1')); // the only day: stays on
    expect(screen.getByTestId('flow-schedule-summary').textContent).toContain('Every Monday at 09:00');
    fireEvent.click(screen.getByTestId('flow-schedule-preset-weekdays'));
    expect(screen.getByTestId('flow-schedule-summary').textContent).toContain('Every Monday to Friday at 09:00');
  });
});
