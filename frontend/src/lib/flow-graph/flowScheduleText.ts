/** Plain-language sentence for a schedule: "Every 5 minutes, 9am to 5pm, Monday to Friday". No cron words, no zone. */
import { parseCron, type CronFields } from './cronFields';
import { WEEKDAYS, cronProblem, cronToPicker } from './flowSchedule';

const pad = (n: number) => String(n).padStart(2, '0');
export const clock = (h: number, m: number) => `${pad(h)}:${pad(m)}`;
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

/** 0 -> "12am", 9 -> "9am", 17 -> "5pm". */
export function hourWord(h: number): string {
  if (h === 0) return '12am';
  if (h < 12) return `${h}am`;
  return h === 12 ? '12pm' : `${h - 12}pm`;
}

export function joinList(items: string[]): string {
  if (items.length <= 1) return items.join('');
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`;
}

const isRun = (xs: number[]) => xs.length >= 3 && xs.every((x, i) => i === 0 || x === xs[i - 1] + 1);

function weekdayPhrase(days: number[]): string {
  if (days.length === 5 && days.join() === '1,2,3,4,5') return 'Monday to Friday';
  if (days.length === 2 && days.join() === '0,6') return 'Saturday and Sunday';
  // Monday-first order reads more naturally than Sunday-first.
  const ordered = [...days].sort((a, b) => ((a + 6) % 7) - ((b + 6) % 7));
  const names = ordered.map((d) => WEEKDAYS[d]);
  if (isRun(ordered.map((d) => (d + 6) % 7))) return `${names[0]} to ${names[names.length - 1]}`;
  return days.length === 1 ? `${names[0]}s` : joinList(names);
}

function minutePhrase(f: CronFields): { text: string; fixed: boolean } {
  const [mi, h] = f.parts;
  const stepMatch = /^\*\/(\d+)$/.exec(mi);
  const every = mi === '*' ? 1 : stepMatch ? Number(stepMatch[1]) : 0;
  const evenly = every > 0 && 60 % every === 0;
  if (evenly) {
    const base = every === 1 ? 'Every minute' : `Every ${every} minutes`;
    if (h === '*') return { text: base, fixed: false };
    const run = isRun(f.hours) || (f.hours.length === 2 && f.hours[1] === f.hours[0] + 1);
    if (run) return { text: `${base}, ${hourWord(f.hours[0])} to ${hourWord(f.hours[f.hours.length - 1])}`, fixed: false };
    return { text: `${base}, ${f.hours.length === 1 ? `during the ${hourWord(f.hours[0])} hour` : `during ${joinList(f.hours.map(hourWord))}`}`, fixed: false };
  }
  const hoursEvery = /^\*\/(\d+)$/.exec(h);
  if (h === '*' || (hoursEvery && 24 % Number(hoursEvery[1]) === 0)) {
    const minutes = f.minutes.length === 1 ? `at minute ${pad(f.minutes[0])}` : `at minutes ${joinList(f.minutes.map(pad))}`;
    if (h === '*') return { text: `Every hour ${minutes}`, fixed: false };
    const n = Number(hoursEvery![1]);
    return { text: n === 1 ? `Every hour ${minutes}` : `Every ${n} hours from midnight, ${minutes}`, fixed: false };
  }
  const times = f.hours.flatMap((hr) => f.minutes.map((m) => clock(hr, m)));
  if (times.length <= 6) return { text: `At ${joinList(times)}`, fixed: true };
  if (isRun(f.hours) && f.minutes.length === 1) {
    const at = f.minutes[0] === 0 ? '' : ` at minute ${pad(f.minutes[0])}`;
    return { text: `Every hour from ${hourWord(f.hours[0])} to ${hourWord(f.hours[f.hours.length - 1])}${at}`, fixed: false };
  }
  return { text: `${times.length} times a day, from ${times[0]} to ${times[times.length - 1]}`, fixed: false };
}

function dayPhrase(f: CronFields, fixedTime: boolean): string {
  const dayParts: string[] = [];
  if (!f.anyDay) {
    const days = f.days.map(String);
    if (f.lastDay) dayParts.push(f.days.length ? `on day ${joinList(days)} and the last day of the month` : 'on the last day of the month');
    else dayParts.push(days.length === 1 ? `on day ${days[0]} of the month` : `on days ${joinList(days)} of the month`);
  }
  if (!f.anyWeekday) dayParts.push(weekdayPhrase(f.weekdays));
  if (dayParts.length === 0) return fixedTime ? 'every day' : '';
  // A cron with both a day of the month and a weekday runs when either matches.
  return dayParts.join(' or ');
}

function monthPhrase(f: CronFields): string {
  if (f.months.length === 12) return '';
  const names = f.months.map((m) => MONTHS[m - 1]);
  if (isRun(f.months)) return `from ${names[0]} to ${names[names.length - 1]}`;
  return `in ${joinList(names)}`;
}

/** Sentence for any valid cron. Friendly shapes keep short, familiar wording; everything else is spelled out. */
export function describeCron(cron: string | undefined): string {
  if (cronProblem(cron)) return 'No valid schedule yet.';
  const f = parseCron(cron)!;
  const p = cronToPicker(cron);
  const at = clock(p.hour, p.minute);
  switch (p.kind) {
    case 'minutes':
      return p.every === 1 ? 'Every minute' : `Every ${p.every} minutes`;
    case 'hours': {
      if (p.every === 1) return p.minute === 0 ? 'Every hour, on the hour' : `Every hour at minute ${pad(p.minute)}`;
      const sample = [0, 1, 2].map((i) => clock(i * p.every, p.minute)).join(', ');
      return `Every ${p.every} hours from midnight (${sample} and so on)`;
    }
    case 'daily':
      return `Every day at ${at}`;
    case 'weekly': {
      const days = weekdayPhrase(p.weekdays);
      return p.weekdays.length === 1 ? `Every ${WEEKDAYS[p.weekdays[0]]} at ${at}` : `Every ${days} at ${at}`;
    }
    case 'monthly':
      return p.monthday === 'last' ? `On the last day of every month at ${at}` : `On day ${p.monthday} of every month at ${at}`;
    default: {
      const time = minutePhrase(f);
      const parts = [time.text, dayPhrase(f, time.fixed), monthPhrase(f)].filter(Boolean);
      return parts.join(', ');
    }
  }
}

/** True when the schedule runs at one fixed wall-clock time each time it fires (so "shows as HH:MM in your browser" makes sense). */
export function fixedClockTime(cron: string | undefined): { hour: number; minute: number } | null {
  const f = parseCron(cron);
  if (!f || f.hours.length !== 1 || f.minutes.length !== 1 || f.parts[0].includes('*') || f.parts[1].includes('*')) return null;
  return { hour: f.hours[0], minute: f.minutes[0] };
}
