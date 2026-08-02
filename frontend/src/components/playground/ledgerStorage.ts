import type { PlaygroundConfig } from './types';

/**
 * Run ledger persistence. Entries are stored per site + user (derived from
 * `window.frappe.boot` when available) and capped at MAX_ENTRIES.
 */

export interface LedgerEntry {
  id: string;
  ranAt: number;
  status: 'ok' | 'held';
  model: string;
  latencyMs?: number;
  tokens?: number;
  config: PlaygroundConfig;
}

const MAX_ENTRIES = 50;

function storageKey(): string {
  const boot = (
    window as unknown as {
      frappe?: { boot?: { sitename?: string; user?: { name?: string } } };
    }
  ).frappe?.boot;
  const site = boot?.sitename || 'site';
  const user = boot?.user?.name || 'user';
  return `huf.playground.run-ledger.${site}.${user}`;
}

export function loadLedgerEntries(): LedgerEntry[] {
  try {
    const raw = window.localStorage.getItem(storageKey());
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((entry) => entry && typeof entry.id === 'string' && entry.config)
      .slice(0, MAX_ENTRIES);
  } catch {
    return [];
  }
}

export function saveLedgerEntries(entries: LedgerEntry[]): void {
  try {
    window.localStorage.setItem(storageKey(), JSON.stringify(entries.slice(0, MAX_ENTRIES)));
  } catch {
    // Storage full / unavailable — the ledger stays in memory for the session.
  }
}

export { MAX_ENTRIES };
