/** Types for the Solutions API (see huf.ai.solutions.read_models / crud). */

export type SolutionPurpose = 'answer' | 'orders' | 'support' | 'bookings' | 'updates' | 'team' | 'custom';
export type SolutionStatus = 'Live' | 'Paused';

export type SolutionErrorCode =
  | 'shared_template'
  | 'cap_exceeds_ceiling'
  | 'scope_loosening'
  | 'not_permitted'
  | 'not_found'
  | 'invalid_payload';

export interface SolutionError {
  code: SolutionErrorCode | string;
  message: string;
}

export interface RunsOn {
  gateway: string;
  label: string;
  phone: string;
}

export interface SolutionPrimary {
  type: 'Agent' | 'Flow';
  name: string;
  label: string;
}

export interface SolutionSummary {
  name: string;
  title: string;
  purpose: SolutionPurpose;
  status: SolutionStatus;
  test_mode: boolean;
  runs_on: RunsOn[];
  shared: boolean;
  entry_count: number;
  primary: SolutionPrimary | null;
  chats_7d: number;
  /** Not in the frozen contract; rendered when the backend supplies it. */
  description?: string;
}

export interface BlameShare {
  solution: string;
  share_pct: number;
}

export interface SolutionOverview extends SolutionSummary {
  description: string;
  health: {
    state: 'ok' | 'warn' | 'bad';
    gateway: string;
    quality: string | null;
    blame: BlameShare | null;
  };
  reach: { contacts_7d: number; new_7d: number };
  activity: Array<{ ts: string; kind: string; text: string }>;
  cost: { sends_24h: number; cap_share: number; ceiling: number | null };
  limits: { per_day: number | null; scope: string | null };
}

export type EntryMatchType =
  | 'Keyword'
  | 'Ad or link tag'
  | 'Catch-all'
  | 'Any conversation'
  | 'Direct message'
  | 'Room or channel'
  | 'Thread'
  | 'Sender';

export interface EntryPoint {
  name: string;
  gateway: string;
  priority: number;
  match_type: EntryMatchType;
  match_values: string[];
  target_type: 'Agent' | 'Flow' | 'Triage';
  agent: string | null;
  flow: string | null;
  cap_per_day: number | null;
  scope_override: string | null;
  allow_first_message: boolean;
  ceiling: number | null;
  ceiling_source: 'meta_tier' | 'gateway_cap' | 'none';
}

export interface NumberSummary {
  gateway: string;
  label: string;
  phone: string;
  solutions: Array<{
    name: string;
    title: string;
    status: SolutionStatus;
    usage_pct: number | null;
    sends_24h: number;
  }>;
  routing_order: Array<{ rank: number; kind: string; label: string; solution: string }>;
  quality: { rating: string | null; source: 'meta' | 'unknown' };
  blame: BlameShare | null;
}

export type RouteReason =
  | 'referral'
  | 'triage_answer'
  | 'pin'
  | 'keyword'
  | 'catch_all'
  | 'default'
  | 'triage_prompt'
  | 'unrouted';

export interface RouteDecision {
  solution: string | null;
  target_type: string | null;
  agent: string | null;
  flow: string | null;
  binding: string | null;
  reason: RouteReason;
  pin: { solution: string; expires_at: string } | null;
  trace: Array<{ k: 'win' | 'skip' | 'info'; t: string }>;
  reply_text: string | null;
}

export interface SimulateRequest {
  gateway: string;
  text: string;
  ref?: string;
  state: {
    pin?: { solution: string; hours_left: number };
    triage_pending?: boolean;
  };
  keyword_beats_pin?: boolean;
}

export type IntentEntryKind = 'keywords' | 'catchall' | 'allowlist' | 'none';

export interface Intent {
  id: SolutionPurpose | string;
  name: string;
  desc: string;
  icon: string;
  sample_name: string;
  entry: IntentEntryKind;
  keywords: string[];
  ref: string;
  suggested_templates: string[];
  policy: string[];
}

export interface SolutionConversation {
  contact: string;
  preview: string;
  solution: string | null;
  gateway: string;
  ts: string;
}

export interface CreateEntryInput {
  match_type: EntryMatchType;
  match_values: string[];
  cap_per_day?: number;
}

export interface CreateSolutionPayload {
  title: string;
  purpose?: SolutionPurpose;
  mode: 'intent' | 'existing' | 'blank';
  existing_target?: { type: 'Agent' | 'Flow'; name: string };
  gateway: string;
  entries: CreateEntryInput[];
  inbound: boolean;
  templates: string[];
  draft_template?: Record<string, unknown>;
  test_mode: boolean;
}

export type UpdateSolutionFields = Partial<
  Pick<SolutionSummary, 'title' | 'purpose' | 'description'> & { test_mode: boolean }
>;

export type SaveEntryPointPayload = Partial<EntryPoint>;

export interface Pin {
  solution: string;
  expires_at?: string;
}
