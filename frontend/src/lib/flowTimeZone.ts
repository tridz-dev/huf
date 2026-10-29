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
  return off ? `${zone} (${off})` : zone;
}

export function browserZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

/**
 * One sentence for the schedule editor: schedules run in the site's time zone, and this shows how that
 * compares with the browser.
 */
export function scheduleZoneSentence(siteZone: string | null | undefined): string {
  if (!siteZone) return 'Schedules run in the time zone of this site.';
  const browser = browserZone();
  const base = `Times here are in the site's time zone: ${describeZone(siteZone)}.`;
  return browser === siteZone
    ? base
    : `${base} Your browser is in ${describeZone(browser)}, so run times in the history appear shifted by the difference.`;
}

/** Short zone note for run lists: the browser zone, which is the zone run times are shown in. */
export function runTimesSentence(siteZone: string | null | undefined): string {
  const browser = browserZone();
  const shown = `Times are shown in your browser's time zone: ${describeZone(browser)}.`;
  if (!siteZone || siteZone === browser) return shown;
  return `${shown} Schedules use the site's time zone: ${describeZone(siteZone)}.`;
}
