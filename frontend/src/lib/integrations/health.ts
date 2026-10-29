/**
 * What the Integrations screens say about one saved connection.
 *
 * One status per connection, worked out from the last Test connection (never from the Active switch alone):
 *   Connected       the last check passed and nothing has gone wrong since
 *   Needs attention the last check was refused, or a step failed after the last good check
 *   Not connected   the last check found no (or incomplete) credentials
 *   Inactive        switched off by the user
 *   Not checked yet saved, never tested
 *   Active          services that have no Test connection (Telegram, GitHub...): on, nothing known to be wrong
 */
import { TESTABLE_SERVICES } from '@/data/integrationGuides';
import { getServiceIdentity } from '@/data/serviceIdentity';
import type { ConnectionTestResult } from '@/services/integrationApi';
import type { IntegrationSettingsDoc } from '@/types/integration.types';

export type HealthKind = 'connected' | 'attention' | 'not_connected' | 'inactive' | 'unchecked' | 'active';

export interface IntegrationHealth {
  kind: HealthKind;
  /** The one word shown in the status pill. */
  label: string;
  /** Pill tone, matching the Badge pill variants. */
  tone: 'good' | 'warning' | 'danger' | 'neutral';
  /** Plain sentence that explains the status (empty when the pill says it all). */
  detail: string;
  /** True when the best next step is to open the credentials. */
  needsCredentials: boolean;
}

type HealthInput = Pick<
  IntegrationSettingsDoc,
  'service' | 'is_active' | 'last_error' | 'last_test_status' | 'last_test_message' | 'account_label'
>;

export function isTestable(service: string): boolean {
  return TESTABLE_SERVICES.includes(service);
}

export function integrationHealth(setting: HealthInput): IntegrationHealth {
  const error = (setting.last_error || '').trim();
  const message = (setting.last_test_message || '').trim();
  if (!setting.is_active) {
    return { kind: 'inactive', label: 'Inactive', tone: 'neutral', detail: 'Switched off. Agents and flows skip it.', needsCredentials: false };
  }
  if (!isTestable(setting.service)) {
    return error
      ? { kind: 'attention', label: 'Needs attention', tone: 'warning', detail: error, needsCredentials: false }
      : { kind: 'active', label: 'Active', tone: 'good', detail: '', needsCredentials: false };
  }
  switch (setting.last_test_status) {
    case 'Connected':
      return error
        ? { kind: 'attention', label: 'Needs attention', tone: 'warning', detail: error, needsCredentials: false }
        : { kind: 'connected', label: 'Connected', tone: 'good', detail: message, needsCredentials: false };
    case 'Rejected':
      return { kind: 'attention', label: 'Needs attention', tone: 'warning', detail: message || error, needsCredentials: true };
    case 'Not connected':
      return { kind: 'not_connected', label: 'Not connected', tone: 'neutral', detail: message || 'No credentials saved yet.', needsCredentials: true };
    default:
      return error
        ? { kind: 'attention', label: 'Needs attention', tone: 'warning', detail: error, needsCredentials: false }
        : { kind: 'unchecked', label: 'Not checked yet', tone: 'neutral', detail: 'Press Test connection to check it.', needsCredentials: false };
  }
}

/** "Slack", "Slack · Tridz", or the name the user gave it. Never the auto id (slack-0018). */
export function integrationTitle(setting: Pick<IntegrationSettingsDoc, 'service' | 'display_label' | 'account_label'>): string {
  const label = (setting.display_label || '').trim();
  if (label) return label;
  const service = getServiceIdentity(setting.service).title;
  const account = (setting.account_label || '').trim();
  return account ? `${service} · ${account}` : service;
}

/** Same service, nothing that tells it apart: these are shown as one group instead of a wall of identical cards. */
export function isPlainDuplicate(setting: IntegrationSettingsDoc): boolean {
  return !setting.is_active && !(setting.display_label || '').trim() && !(setting.account_label || '').trim();
}

export interface ServiceGroup {
  service: string;
  title: string;
  items: IntegrationSettingsDoc[];
}

/** Inactive, unnamed connections grouped by service ("Google Sheets, 6"); everything else stays on its own. */
export function groupInactiveDuplicates(items: IntegrationSettingsDoc[]): {
  visible: IntegrationSettingsDoc[];
  groups: ServiceGroup[];
} {
  const visible: IntegrationSettingsDoc[] = [];
  const byService = new Map<string, IntegrationSettingsDoc[]>();
  for (const item of items) {
    if (isPlainDuplicate(item)) {
      byService.set(item.service, [...(byService.get(item.service) ?? []), item]);
    } else {
      visible.push(item);
    }
  }
  const groups: ServiceGroup[] = [];
  for (const [service, list] of byService) {
    if (list.length === 1) visible.push(list[0]);
    else groups.push({ service, title: getServiceIdentity(service).title, items: list });
  }
  return { visible, groups };
}

const ORDER: Record<HealthKind, number> = { attention: 0, not_connected: 1, unchecked: 2, connected: 3, active: 3, inactive: 4 };

/** Things that need a person first, working ones next, switched-off last. Stable within each rank. */
export function sortByHealth(items: IntegrationSettingsDoc[]): IntegrationSettingsDoc[] {
  return items
    .map((item, index) => ({ item, index, rank: ORDER[integrationHealth(item).kind] }))
    .sort((a, b) => a.rank - b.rank || a.index - b.index)
    .map(({ item }) => item);
}

/**
 * The status the details page shows: the newest check made on the page (`live`), otherwise what was saved.
 * `fixLabel` names the credentials button when the answer points at the credentials.
 */
export function deriveStatus(
  saved: HealthInput,
  live: { result: ConnectionTestResult; unsaved: boolean } | null,
  isNew: boolean,
): { health: IntegrationHealth | null; fixLabel: string | undefined } {
  let health: IntegrationHealth | null = null;
  if (live) {
    const r = live.result;
    health =
      r.code === 'unreachable'
        ? { kind: 'unchecked', label: 'Could not check', tone: 'neutral', detail: r.message, needsCredentials: false }
        : integrationHealth({
            ...saved,
            is_active: 1,
            last_test_status: r.status,
            last_test_message: r.message,
            last_error: r.status === 'Connected' && !live.unsaved ? '' : saved.last_error,
          });
  } else if (!isNew) {
    health = integrationHealth(saved);
  }
  if (health?.kind === 'attention' && saved.last_error && health.detail === saved.last_error) {
    health = { ...health, detail: 'A step reported a problem after the last check.' };
  }
  const code = live?.result.code;
  const fixLabel =
    code === 'missing_credentials'
      ? 'Add the missing credentials'
      : code === 'no_credentials' || (!live && health?.kind === 'not_connected')
        ? 'Add credentials'
        : code === 'rejected' || code === 'missing_permission' || (!live && health?.needsCredentials)
          ? 'Update credentials'
          : undefined;
  return { health, fixLabel };
}
