/**
 * Reads a 5-part cron (`minute hour day month weekday`) into the exact numbers it allows. Shared by the validity
 * check, the plain-language summary and the "next runs" list, so all three always agree.
 */

const MONTH_NAMES = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];
const DAY_NAMES = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'];

/** [low, high] per position: minute, hour, day of month, month, weekday (0 and 7 are both Sunday). */
export const CRON_LIMITS: Array<[number, number]> = [[0, 59], [0, 23], [1, 31], [1, 12], [0, 7]];

export interface CronFields {
  /** The five raw parts, trimmed. */
  parts: string[];
  minutes: number[];
  hours: number[];
  /** 1..31; empty when the part is only `L`. */
  days: number[];
  months: number[];
  /** 0 (Sunday) .. 6. */
  weekdays: number[];
  /** `*` in the day-of-month / weekday position. */
  anyDay: boolean;
  anyWeekday: boolean;
  /** The day-of-month part contains `L` (the last day of the month). */
  lastDay: boolean;
}

function atom(token: string, position: number): number | null {
  if (/^\d+$/.test(token)) return Number(token);
  const t = token.toLowerCase();
  if (position === 3) {
    const i = MONTH_NAMES.indexOf(t);
    return i < 0 ? null : i + 1;
  }
  if (position === 4) {
    const i = DAY_NAMES.indexOf(t);
    return i < 0 ? null : i;
  }
  return null;
}

/** Every number one part allows, or null when the part is malformed or out of range. `L` is reported separately. */
function expand(part: string, position: number): { values: number[]; last: boolean } | null {
  const [low, high] = CRON_LIMITS[position];
  const values = new Set<number>();
  let last = false;
  for (const item of part.split(',')) {
    if (!item) return null;
    const [base, stepText, extra] = item.split('/');
    if (extra !== undefined) return null;
    let step = 1;
    if (stepText !== undefined) {
      if (!/^\d+$/.test(stepText) || Number(stepText) < 1) return null;
      step = Number(stepText);
    }
    if (base === 'L' && position === 2 && stepText === undefined) {
      last = true;
      continue;
    }
    let from: number;
    let to: number;
    if (base === '*') {
      from = low;
      to = position === 4 ? 6 : high;
    } else if (base.includes('-')) {
      const [a, b, more] = base.split('-');
      if (more !== undefined) return null;
      const na = atom(a, position);
      const nb = atom(b, position);
      if (na === null || nb === null || na > nb) return null;
      from = na;
      to = nb;
    } else {
      const n = atom(base, position);
      if (n === null) return null;
      from = n;
      // `5/15` means "from 5, every 15"; a bare number is just itself.
      to = stepText === undefined ? n : high;
    }
    if (from < low || to > high || from > to) return null;
    for (let v = from; v <= to; v += step) values.add(position === 4 && v === 7 ? 0 : v);
  }
  return { values: [...values].sort((a, b) => a - b), last };
}

/** The numbers a cron allows, or null when it is not a well-formed 5-part cron. */
export function parseCron(cron: string | undefined): CronFields | null {
  const parts = (cron ?? '').trim().split(/\s+/);
  if (parts.length !== 5 || !parts[0]) return null;
  const out = parts.map((p, i) => expand(p, i));
  if (out.some((o) => o === null)) return null;
  const [mi, h, d, mo, dow] = out as Array<{ values: number[]; last: boolean }>;
  return {
    parts,
    minutes: mi.values,
    hours: h.values,
    days: d.values,
    months: mo.values,
    weekdays: dow.values,
    anyDay: parts[2] === '*',
    anyWeekday: parts[4] === '*',
    lastDay: d.last,
  };
}
