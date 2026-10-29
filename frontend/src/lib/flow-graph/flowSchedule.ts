/**
 * Friendly schedule <-> 5-part cron (`minute hour day month dow`). The Flow node stores `cron` (and, when the author
 * chose one, `time_zone`; see docs/flow/FIELD_CONTRACT.md); the picker compiles to it and reads it back.
 */
import { CRON_LIMITS, parseCron } from '../flow-trigger/cronFields';

export type ScheduleKind = 'minutes' | 'hours' | 'daily' | 'weekly' | 'monthly' | 'custom';

export interface SchedulePicker {
  kind: ScheduleKind;
  /** every N minutes / hours */
  every: number;
  minute: number;
  hour: number;
  /** 0 (Sunday) .. 6; at least one */
  weekdays: number[];
  /** 1..31 or `last` */
  monthday: number | 'last';
}

export const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

/** Intervals that divide the hour / the day evenly, so "every N" really is every N from the top of the hour / midnight. */
export const MINUTE_STEPS = [1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30];
export const HOUR_STEPS = [1, 2, 3, 4, 6, 8, 12];

export const DEFAULT_PICKER: SchedulePicker = { kind: 'daily', every: 15, minute: 0, hour: 9, weekdays: [1], monthday: 1 };

/** Sensible starting values when the user switches kind (never carry minutes into hours: 15 hours is not what they meant). */
export function pickerForKind(kind: ScheduleKind, from: SchedulePicker): SchedulePicker {
  if (kind === from.kind) return from;
  if (kind === 'minutes') return { ...from, kind, every: 15 };
  if (kind === 'hours') return { ...from, kind, every: 1, minute: 0 };
  return { ...from, kind };
}

const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, Number.isFinite(n) ? Math.trunc(n) : lo));

/** `1,2,3,4,5` becomes `1-5`; any other set stays a comma list. */
function weekdayPart(days: number[]): string {
  const set = [...new Set(days.map((d) => clamp(d, 0, 6)))].sort((a, b) => a - b);
  if (set.length === 0 || set.length === 7) return '*';
  const isRun = set.length >= 3 && set.every((d, i) => i === 0 || d === set[i - 1] + 1);
  return isRun ? `${set[0]}-${set[set.length - 1]}` : set.join(',');
}

export function pickerToCron(p: SchedulePicker): string {
  const minute = clamp(p.minute, 0, 59);
  const hour = clamp(p.hour, 0, 23);
  switch (p.kind) {
    case 'minutes':
      return `*/${clamp(p.every, 1, 59)} * * * *`;
    case 'hours': {
      const n = clamp(p.every, 1, 23);
      // 24 divides evenly: every n hours from midnight. Anything else is spelled out so the gaps are never a surprise.
      return `${minute} ${24 % n === 0 ? `*/${n}` : Array.from({ length: Math.ceil(24 / n) }, (_, i) => i * n).join(',')} * * *`;
    }
    case 'daily':
      return `${minute} ${hour} * * *`;
    case 'weekly':
      return `${minute} ${hour} * * ${weekdayPart(p.weekdays)}`;
    case 'monthly':
      return `${minute} ${hour} ${p.monthday === 'last' ? 'L' : clamp(p.monthday, 1, 31)} * *`;
    default:
      return '';
  }
}

const INT = /^\d+$/;
const STEP = /^\*\/(\d+)$/;

/** Recover the picker from a cron string, or `custom` when it is not one of the friendly shapes. */
export function cronToPicker(cron: string | undefined): SchedulePicker {
  const text = (cron ?? '').trim();
  const parts = text.split(/\s+/);
  const custom = (): SchedulePicker => ({ ...DEFAULT_PICKER, kind: 'custom' });
  if (!text) return { ...DEFAULT_PICKER, kind: 'daily' };
  if (parts.length !== 5 || !parseCron(text)) return custom();
  const [mi, h, d, mo, dow] = parts;
  const base = { ...DEFAULT_PICKER };
  if (mo !== '*') return custom();
  if (h === '*' && d === '*' && dow === '*' && STEP.test(mi)) {
    const every = Number(STEP.exec(mi)![1]);
    return MINUTE_STEPS.includes(every) ? { ...base, kind: 'minutes', every } : custom();
  }
  if (INT.test(mi) && d === '*' && dow === '*') {
    if (STEP.test(h)) {
      const every = Number(STEP.exec(h)![1]);
      return HOUR_STEPS.includes(every) ? { ...base, kind: 'hours', every, minute: Number(mi) } : custom();
    }
    if (h === '*') return { ...base, kind: 'hours', every: 1, minute: Number(mi) };
  }
  if (INT.test(mi) && INT.test(h)) {
    const time = { minute: Number(mi), hour: Number(h) };
    if (d === '*' && dow === '*') return { ...base, ...time, kind: 'daily' };
    if (d === '*') {
      const fields = parseCron(text)!;
      return { ...base, ...time, kind: 'weekly', weekdays: fields.weekdays.length ? fields.weekdays : [1] };
    }
    if (dow === '*' && (INT.test(d) || d === 'L')) {
      return { ...base, ...time, kind: 'monthly', monthday: d === 'L' ? 'last' : Number(d) };
    }
  }
  return custom();
}

const FIELD = /^(\*|L|[A-Za-z]{3}|\d+)(-([A-Za-z]{3}|\d+))?(\/\d+)?(,(\*|L|[A-Za-z]{3}|\d+)(-([A-Za-z]{3}|\d+))?(\/\d+)?)*$/;

/** Plain-language problem with a cron string, or null when it is a well-formed 5-part cron. */
export function cronProblem(cron: string | undefined): string | null {
  const text = (cron ?? '').trim();
  if (!text) return 'Choose when this flow should run.';
  const parts = text.split(/\s+/);
  if (parts.length !== 5) return 'A schedule needs 5 parts: minute hour day month weekday (for example 0 9 * * 1).';
  if (!parts.every((p) => FIELD.test(p))) return 'One of the schedule parts is not valid. Use numbers, *, ranges like 1-5, or steps like */15.';
  if (!parseCron(text)) {
    return `One of the schedule numbers is out of range: minute ${CRON_LIMITS[0].join('-')}, hour ${CRON_LIMITS[1].join('-')}, day 1-31, month 1-12, weekday 0-6.`;
  }
  return null;
}
