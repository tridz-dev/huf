/** Helpers that name time zones in plain words, so schedule times and run times can be compared. */

/** "UTC+05:30" for a zone at a moment (default now). Falls back to the zone name alone. */
export function zoneOffsetLabel(zone: string, at: Date = new Date()): string {
  try {
    const parts = new Intl.DateTimeFormat('en-US', { timeZone: zone, timeZoneName: 'longOffset' }).formatToParts(at);
    const raw = parts.find((p) => p.type === 'timeZoneName')?.value ?? '';
    // "GMT+05:30" or "GMT" (UTC itself)
    const m = /^GMT([+-]\d{2}:\d{2})$/.exec(raw);
    if (!m) return 'UTC';
    return m[1] === '+00:00' ? 'UTC' : `UTC${m[1]}`;
  } catch {
    return '';
  }
}

/** "Asia/Kolkata (UTC+05:30)". */
export function describeZone(zone: string | null | undefined, at: Date = new Date()): string {
  if (!zone) return '';
  const off = zoneOffsetLabel(zone, at);
  return off && off !== zone ? `${zone} (${off})` : zone;
}

export function browserZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

const unique = (names: Array<string | null | undefined>) => [...new Set(names.filter((n): n is string => Boolean(n)))].sort((a, b) => (a === 'UTC' ? -1 : b === 'UTC' ? 1 : a.localeCompare(b)));

/**
 * Every time zone name the browser knows (plus UTC and any `include`d names, because a browser lists only one spelling per
 * zone, e.g. Asia/Calcutta for Asia/Kolkata), alphabetical; a short built-in list when the browser cannot list them.
 */
export function allTimeZones(...include: Array<string | null | undefined>): string[] {
  const fallback = ['UTC', 'Asia/Kolkata', 'Asia/Dubai', 'Asia/Singapore', 'Asia/Tokyo', 'Europe/London', 'Europe/Berlin', 'America/New_York', 'America/Chicago', 'America/Los_Angeles', 'Australia/Sydney'];
  try {
    const list = (Intl as unknown as { supportedValuesOf?: (key: string) => string[] }).supportedValuesOf?.('timeZone') ?? fallback;
    return unique(['UTC', ...list, ...include]);
  } catch {
    return unique([...fallback, ...include]);
  }
}

/**
 * The one line under a schedule that says which clock it runs on: "Runs in Asia/Kolkata time (UTC+05:30), this site's time zone."
 * A time chosen by the author reads "Runs in Europe/London time (UTC+00:00)." with no claim about the site.
 */
export function scheduleZoneLine(zone: string | null | undefined, isSiteZone: boolean): string {
  if (!zone) return 'Runs in the time zone of this site.';
  return `Runs in ${describeZone(zone).replace(' (', ' time (')}${isSiteZone ? ", this site's time zone" : ''}.`;
}

/** "Shows as 03:30 in your browser (UTC)": how a fixed run time reads where the person is, or '' when the clocks agree. */
export function browserTimeNote(shownAs: string, zone: string | null | undefined): string {
  const browser = browserZone();
  if (!zone || browser === zone) return '';
  return `Shows as ${shownAs} in your browser (${browser}).`;
}

/** Short zone note for run lists: the browser zone, which is the zone run times are shown in. */
export function runTimesSentence(siteZone: string | null | undefined): string {
  const browser = browserZone();
  const shown = `Times are shown in your browser's time zone: ${describeZone(browser)}.`;
  if (!siteZone || siteZone === browser) return shown;
  return `${shown} Schedules use the site's time zone: ${describeZone(siteZone)}.`;
}
