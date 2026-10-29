/**
 * Friendly schedule <-> 5-part cron (`minute hour day month dow`), evaluated in server system time.
 * The Flow node only stores `cron` (see docs/flow/FIELD_CONTRACT.md); the picker compiles to it.
 */
export type ScheduleKind = 'minutes' | 'hours' | 'daily' | 'weekly' | 'monthly' | 'custom';

export interface SchedulePicker {
  kind: ScheduleKind;
  /** every N minutes / hours */
  every: number;
  minute: number;
  hour: number;
  /** 0 (Sunday) .. 6 */
  weekday: number;
  /** 1..28 */
  monthday: number;
}

export const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

export const DEFAULT_PICKER: SchedulePicker = { kind: 'daily', every: 15, minute: 0, hour: 9, weekday: 1, monthday: 1 };

const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, Number.isFinite(n) ? Math.trunc(n) : lo));

export function pickerToCron(p: SchedulePicker): string {
  const minute = clamp(p.minute, 0, 59);
  const hour = clamp(p.hour, 0, 23);
  switch (p.kind) {
    case 'minutes':
      return `*/${clamp(p.every, 1, 59)} * * * *`;
    case 'hours':
      return `${minute} */${clamp(p.every, 1, 23)} * * *`;
    case 'daily':
      return `${minute} ${hour} * * *`;
    case 'weekly':
      return `${minute} ${hour} * * ${clamp(p.weekday, 0, 6)}`;
    case 'monthly':
      return `${minute} ${hour} ${clamp(p.monthday, 1, 28)} * *`;
    default:
      return '';
  }
}

const INT = /^\d+$/;

/** Recover the picker from a cron string, or `custom` when it is not one of the friendly shapes. */
export function cronToPicker(cron: string | undefined): SchedulePicker {
  const parts = (cron ?? '').trim().split(/\s+/);
  if (parts.length !== 5 || !parts[0]) return { ...DEFAULT_PICKER, kind: cron?.trim() ? 'custom' : 'daily' };
  const [mi, h, d, mo, dow] = parts;
  const base = { ...DEFAULT_PICKER };
  const step = /^\*\/(\d+)$/;
  if (h === '*' && d === '*' && mo === '*' && dow === '*' && step.test(mi)) {
    return { ...base, kind: 'minutes', every: Number(step.exec(mi)![1]) };
  }
  if (INT.test(mi) && step.test(h) && d === '*' && mo === '*' && dow === '*') {
    return { ...base, kind: 'hours', every: Number(step.exec(h)![1]), minute: Number(mi) };
  }
  if (INT.test(mi) && INT.test(h) && mo === '*') {
    if (d === '*' && dow === '*') return { ...base, kind: 'daily', minute: Number(mi), hour: Number(h) };
    if (d === '*' && INT.test(dow) && Number(dow) <= 6) {
      return { ...base, kind: 'weekly', minute: Number(mi), hour: Number(h), weekday: Number(dow) };
    }
    if (dow === '*' && INT.test(d) && Number(d) >= 1 && Number(d) <= 28) {
      return { ...base, kind: 'monthly', minute: Number(mi), hour: Number(h), monthday: Number(d) };
    }
  }
  return { ...base, kind: 'custom' };
}

const FIELD = /^(\*|\d+(-\d+)?)(\/\d+)?(,(\*|\d+(-\d+)?)(\/\d+)?)*$/;

const LIMITS: Array<[number, number]> = [[0, 59], [0, 23], [1, 31], [1, 12], [0, 7]];

/** True when every number in one cron part is inside the allowed range for that position. */
function partInRange(part: string, [lo, hi]: [number, number]): boolean {
  return part.split(',').every((item) => {
    const [base, step] = item.split('/');
    if (step !== undefined && Number(step) < 1) return false;
    if (base === '*') return true;
    const [from, to] = base.split('-').map(Number);
    return from >= lo && from <= hi && (to === undefined || (to >= from && to <= hi));
  });
}

/** Plain-language problem with a cron string, or null when it is a well-formed 5-part cron. */
export function cronProblem(cron: string | undefined): string | null {
  const text = (cron ?? '').trim();
  if (!text) return 'Choose when this flow should run.';
  const parts = text.split(/\s+/);
  if (parts.length !== 5) return 'A schedule needs 5 parts: minute hour day month weekday (for example 0 9 * * 1).';
  if (!parts.every((p) => FIELD.test(p))) return 'One of the schedule parts is not valid. Use numbers, *, ranges like 1-5, or steps like */15.';
  if (!parts.every((p, i) => partInRange(p, LIMITS[i]))) {
    return 'One of the schedule numbers is out of range: minute 0-59, hour 0-23, day 1-31, month 1-12, weekday 0-6.';
  }
  return null;
}

const pad = (n: number) => String(n).padStart(2, '0');
const time = (h: number, m: number) => `${pad(h)}:${pad(m)}`;

/** Human-readable preview, e.g. "Every Monday at 09:00 (server time)". */
export function describeCron(cron: string | undefined): string {
  if (cronProblem(cron)) return 'No valid schedule yet.';
  const p = cronToPicker(cron);
  switch (p.kind) {
    case 'minutes':
      return `Every ${p.every === 1 ? 'minute' : `${p.every} minutes`} (server time)`;
    case 'hours':
      return `Every ${p.every === 1 ? 'hour' : `${p.every} hours`} at minute ${pad(p.minute)} (server time)`;
    case 'daily':
      return `Every day at ${time(p.hour, p.minute)} (server time)`;
    case 'weekly':
      return `Every ${WEEKDAYS[p.weekday]} at ${time(p.hour, p.minute)} (server time)`;
    case 'monthly':
      return `On day ${p.monthday} of every month at ${time(p.hour, p.minute)} (server time)`;
    default:
      return `Custom schedule "${(cron ?? '').trim()}" (server time)`;
  }
}
