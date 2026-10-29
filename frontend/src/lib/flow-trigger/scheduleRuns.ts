/** The next times a schedule fires, on the wall clock of a chosen time zone, and how a moment reads in another zone. */
import { parseCron } from './cronFields';

export interface Wall {
  y: number;
  m: number; // 1..12
  d: number;
  h: number;
  mi: number;
}

export interface ScheduledRun {
  wall: Wall;
  /** The real moment, for showing it in another zone. */
  at: Date;
}

const formatters = new Map<string, Intl.DateTimeFormat>();
function zoneFormatter(zone: string): Intl.DateTimeFormat {
  let f = formatters.get(zone);
  if (!f) {
    f = new Intl.DateTimeFormat('en-US', { timeZone: zone, hourCycle: 'h23', year: 'numeric', month: 'numeric', day: 'numeric', hour: 'numeric', minute: 'numeric' });
    formatters.set(zone, f);
  }
  return f;
}

/** The wall-clock time in `zone` at a real moment. */
export function wallIn(zone: string, at: Date): Wall {
  const parts = zoneFormatter(zone).formatToParts(at);
  const n = (type: string) => Number(parts.find((p) => p.type === type)?.value ?? 0);
  return { y: n('year'), m: n('month'), d: n('day'), h: n('hour') % 24, mi: n('minute') };
}

const wallUtc = (w: Wall) => Date.UTC(w.y, w.m - 1, w.d, w.h, w.mi);

/** The real moment a wall-clock time in `zone` happens (the first one when a clock change repeats it; later when it is skipped). */
export function instantOf(zone: string, w: Wall): Date {
  const guess = wallUtc(w);
  let t = guess;
  for (let i = 0; i < 3; i++) {
    const seen = wallUtc(wallIn(zone, new Date(t)));
    const next = t - (seen - guess);
    if (next === t) break;
    t = next;
  }
  return new Date(t);
}

const daysInMonth = (y: number, m: number) => new Date(Date.UTC(y, m, 0)).getUTCDate();

/** The next `count` runs after `from`, read on `zone`'s clock. Empty for an invalid cron or one that never fires. */
export function nextRuns(cron: string | undefined, zone: string, count = 3, from: Date = new Date()): ScheduledRun[] {
  const f = parseCron(cron);
  if (!f) return [];
  const now = wallIn(zone, from);
  const out: ScheduledRun[] = [];
  const nowKey = wallUtc(now);
  for (let offset = 0; offset < 366 * 8 && out.length < count; offset++) {
    const day = new Date(Date.UTC(now.y, now.m - 1, now.d + offset));
    const y = day.getUTCFullYear();
    const m = day.getUTCMonth() + 1;
    const d = day.getUTCDate();
    if (!f.months.includes(m)) continue;
    const dom = f.days.includes(d) || (f.lastDay && d === daysInMonth(y, m));
    const dow = f.weekdays.includes(day.getUTCDay());
    // Cron rule: with both a day of the month and a weekday given, either one matches.
    const matches = f.anyDay && f.anyWeekday ? true : f.anyDay ? dow : f.anyWeekday ? dom : dom || dow;
    if (!matches) continue;
    for (const h of f.hours) {
      for (const mi of f.minutes) {
        const wall = { y, m, d, h, mi };
        if (wallUtc(wall) <= nowKey) continue;
        out.push({ wall, at: instantOf(zone, wall) });
        if (out.length >= count) return out;
      }
    }
  }
  return out;
}

const DAY = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const pad = (n: number) => String(n).padStart(2, '0');

/** "Fri 30 Oct, 09:00". */
export function formatWall(w: Wall): string {
  const dow = new Date(Date.UTC(w.y, w.m - 1, w.d)).getUTCDay();
  return `${DAY[dow]} ${w.d} ${MON[w.m - 1]}, ${pad(w.h)}:${pad(w.mi)}`;
}

/** "HH:MM" of a daily wall-clock time in `from` as it reads in `to` today. */
export function clockInOtherZone(hour: number, minute: number, from: string, to: string, at: Date = new Date()): string {
  const today = wallIn(from, at);
  const instant = instantOf(from, { ...today, h: hour, mi: minute });
  const w = wallIn(to, instant);
  return `${pad(w.h)}:${pad(w.mi)}`;
}
