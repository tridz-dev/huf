import type { GatewayDoc } from '@/services/gatewayApi';

export const SETTINGS_SECTIONS = [
  { key: 'connection', label: 'Connection' },
  { key: 'credentials', label: 'Credentials' },
  { key: 'policy', label: 'Policy' },
  { key: 'access', label: 'Access & consent' },
  { key: 'run-as', label: 'Run as' },
  { key: 'widgets', label: 'Opt-in & widgets' },
  { key: 'hours', label: 'Business hours' },
  { key: 'replies', label: 'Replies & calls' },
  { key: 'danger', label: 'Danger zone' },
  { key: 'facebook', label: 'Facebook signup' },
] as const;

export type SettingsKey = (typeof SETTINGS_SECTIONS)[number]['key'];

export function resolveSection(raw: string | undefined): SettingsKey {
  return SETTINGS_SECTIONS.find((s) => s.key === raw)?.key ?? 'connection';
}

export const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'] as const;

export interface BusinessHourRow {
  weekday: string;
  start_time: string;
  end_time: string;
}

export interface BusinessHolidayRow {
  holiday_date: string;
  description?: string;
}

/** Gateway fields added by the Automation section (not yet in the shared GatewayDoc type). */
export interface AutomationFields {
  run_as_user?: string;
  run_as_role_profile?: string;
  business_hours_enabled?: 0 | 1;
  business_hours?: BusinessHourRow[];
  holidays?: BusinessHolidayRow[];
  /** Optional ERPNext/HRMS Holiday List name (Data, not a Link: the DocType may be absent). */
  holiday_list?: string;
  after_hours_mode?: 'agent_24_7' | 'away_message' | 'away_template';
  away_message?: string;
  away_template?: string;
}

export type GatewayFull = GatewayDoc & AutomationFields;

const FORBIDDEN_RUN_AS = new Set(['administrator', 'guest']);

/** Returns an error message when the user may not be a run-as identity, else null. */
export function validateRunAs(user: string): string | null {
  if (FORBIDDEN_RUN_AS.has(user.trim().toLowerCase())) {
    return 'Administrator and Guest cannot be used as the run-as user.';
  }
  return null;
}
