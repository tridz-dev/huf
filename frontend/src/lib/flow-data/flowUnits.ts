/** Waiting times as people say them (minutes, hours, days) and as the flow stores them (milliseconds or seconds). */
export type TimeUnit = 'seconds' | 'minutes' | 'hours' | 'days';

export const UNIT_SECONDS: Record<TimeUnit, number> = { seconds: 1, minutes: 60, hours: 3600, days: 86400 };
export const UNIT_LABEL: Record<TimeUnit, string> = { seconds: 'seconds', minutes: 'minutes', hours: 'hours', days: 'days' };

/** `1800000 ms` -> `{30, minutes}`: the largest unit that gives a whole number, never smaller than `smallest`. */
export function splitDuration(seconds: number, units: TimeUnit[], smallest: TimeUnit = units[0]): { amount: number; unit: TimeUnit } {
  const ordered = [...units].sort((a, b) => UNIT_SECONDS[b] - UNIT_SECONDS[a]);
  for (const unit of ordered) {
    if (UNIT_SECONDS[unit] < UNIT_SECONDS[smallest]) continue;
    const amount = seconds / UNIT_SECONDS[unit];
    if (Number.isInteger(amount) && amount >= 1) return { amount, unit };
  }
  const unit = smallest;
  return { amount: Math.max(1, Math.round(seconds / UNIT_SECONDS[unit])), unit };
}

export const toSeconds = (amount: number, unit: TimeUnit): number => Math.round(amount * UNIT_SECONDS[unit]);

/** "30 minutes", "1 hour", "2 days". */
export function durationWords(seconds: number, units: TimeUnit[]): string {
  const { amount, unit } = splitDuration(seconds, units);
  const word = amount === 1 ? UNIT_LABEL[unit].replace(/s$/, '') : UNIT_LABEL[unit];
  return `${amount} ${word}`;
}
